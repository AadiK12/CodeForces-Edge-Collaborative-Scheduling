#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using namespace std;

namespace {

enum class RequestState {
    UNSEEN,
    WAITING_FOR_CLOUD,
    P_PRE_RUNNING,
    WAITING_PREFILL_UP,
    P_PROC_READY,
    P_PROC_RUNNING,
    WAITING_PREFILL_DOWN,
    P_POST_READY,
    P_POST_RUNNING,
    D_PRE_READY,
    D_PRE_RUNNING,
    WAITING_DECODE_UP,
    D_PROC_READY,
    D_PROC_RUNNING,
    WAITING_DECODE_DOWN,
    D_POST_READY,
    D_POST_RUNNING,
    FINISHED,
};

enum class TaskKind {
    P_POST,
    D_PRE,
    D_POST,
    P_PROC,
    D_PROC,
};

struct Request {
    int id = -1;
    int input_length = 0;
    int cloud = -1;
    RequestState state = RequestState::UNSEEN;
    uint64_t admission_sequence = 0;
};

struct ReadyTask {
    TaskKind kind;
    int request_id;
    uint64_t sequence;
};

struct TaskTimes {
    int size = 0;
    double prefill_pre = 0;
    double prefill_proc = 0;
    double prefill_post = 0;
    double decode_pre = 0;
    double decode_proc = 0;
    double decode_post = 0;
};

class BaselineScheduler {
  public:
    bool read_startup() {
        if (!(cin >> cloud_count_ >> schedule_cost_ >> latency_ms_ >> bandwidth_gbps_ >>
              bytes_per_token_ >> layer_count_)) {
            return false;
        }

        cin >> slo_tdr_ >> slo_tpot_ >> throughput_upper_bound_ >> throughput_baseline_ >>
            distance_baseline_ >> throughput_weight_ >> latency_weight_;

        int row_count = 0;
        cin >> row_count;
        task_times_.resize(row_count);
        for (TaskTimes& row : task_times_) {
            cin >> row.size >> row.prefill_pre >> row.prefill_proc >> row.prefill_post >>
                row.decode_pre >> row.decode_proc >> row.decode_post;
        }

        cloud_busy_.assign(cloud_count_, false);
        cloud_reserved_.assign(cloud_count_, false);
        cloud_ready_.resize(cloud_count_);
        for (int cloud = 0; cloud < cloud_count_; ++cloud) {
            free_clouds_.push_back(cloud);
        }
        return true;
    }

    void run() {
        string frame_header;
        while (cin >> frame_header) {
            if (frame_header == "END") {
                return;
            }

            // The baseline is purely reactive, so the timestamp is parsed but never predicted.
            current_time_ms_ = stod(frame_header);

            int event_count = 0;
            cin >> event_count;
            d_post_completed_this_frame_.clear();

            for (int event_index = 0; event_index < event_count; ++event_index) {
                string event_type;
                cin >> event_type;
                if (event_type == "ARR") {
                    read_arrival();
                } else if (event_type == "TDN") {
                    read_task_completion();
                } else if (event_type == "XDN") {
                    read_transfer_completion();
                } else if (event_type == "FIN") {
                    read_finish();
                } else {
                    fail("unknown event type: " + event_type);
                }
            }

            finalize_decode_completions();
            vector<string> assignments = dispatch_ready_work();
            print_response(assignments);
        }
    }

  private:
    int cloud_count_ = 0;
    int layer_count_ = 0;
    double schedule_cost_ = 0;
    double latency_ms_ = 0;
    double bandwidth_gbps_ = 0;
    long long bytes_per_token_ = 0;

    double slo_tdr_ = 0;
    double slo_tpot_ = 0;
    double throughput_upper_bound_ = 0;
    double throughput_baseline_ = 0;
    double distance_baseline_ = 0;
    double throughput_weight_ = 0;
    double latency_weight_ = 0;

    double current_time_ms_ = 0;
    uint64_t next_ready_sequence_ = 0;

    vector<TaskTimes> task_times_;
    vector<Request> requests_;

    bool edge_busy_ = false;
    vector<bool> cloud_busy_;

    // Baseline-only policy state: a cloud is reserved by one request until FIN.
    vector<bool> cloud_reserved_;
    deque<int> free_clouds_;

    deque<int> pending_requests_;
    deque<ReadyTask> edge_ready_;
    vector<deque<ReadyTask>> cloud_ready_;

    vector<int> d_post_completed_this_frame_;

    [[noreturn]] void fail(const string& message) const {
        cerr << "baseline scheduler state error at t=" << current_time_ms_ << ": " << message
             << '\n';
        exit(0);
    }

    Request& request(int request_id) {
        if (request_id < 0 || request_id >= static_cast<int>(requests_.size()) ||
            requests_[request_id].state == RequestState::UNSEEN) {
            fail("unknown request " + to_string(request_id));
        }
        return requests_[request_id];
    }

    void expect_state(const Request& req, RequestState expected, const string& event) const {
        if (req.state != expected) {
            fail(event + " arrived while request " + to_string(req.id) +
                 " was in an unexpected state");
        }
    }

    uint64_t new_ready_sequence() {
        return ++next_ready_sequence_;
    }

    void enqueue_edge(TaskKind kind, int request_id) {
        edge_ready_.push_back({kind, request_id, new_ready_sequence()});
    }

    void enqueue_cloud(TaskKind kind, int cloud, int request_id) {
        if (cloud < 0 || cloud >= cloud_count_) {
            fail("invalid cloud " + to_string(cloud));
        }
        cloud_ready_[cloud].push_back({kind, request_id, new_ready_sequence()});
    }

    void read_arrival() {
        int request_id = 0;
        int input_length = 0;
        cin >> request_id >> input_length;

        if (request_id >= static_cast<int>(requests_.size())) {
            requests_.resize(request_id + 1);
        }
        if (requests_[request_id].state != RequestState::UNSEEN) {
            fail("duplicate ARR for request " + to_string(request_id));
        }

        Request& req = requests_[request_id];
        req.id = request_id;
        req.input_length = input_length;
        req.cloud = -1;
        req.state = RequestState::WAITING_FOR_CLOUD;
        req.admission_sequence = new_ready_sequence();
        pending_requests_.push_back(request_id);
    }

    int cloud_from_server(const string& server) const {
        if (server.size() < 2 || server.front() != 'C') {
            fail("invalid cloud server name: " + server);
        }
        int cloud = stoi(server.substr(1));
        if (cloud < 0 || cloud >= cloud_count_) {
            fail("cloud server out of range: " + server);
        }
        return cloud;
    }

    void free_server(const string& server) {
        if (server == "E") {
            if (!edge_busy_) {
                fail("TDN attempted to free an idle edge");
            }
            edge_busy_ = false;
            return;
        }

        int cloud = cloud_from_server(server);
        if (!cloud_busy_[cloud]) {
            fail("TDN attempted to free idle cloud " + to_string(cloud));
        }
        cloud_busy_[cloud] = false;
    }

    vector<int> read_group_members(int member_count) {
        if (member_count < 1) {
            fail("group with no members");
        }
        vector<int> members(member_count);
        for (int& request_id : members) {
            cin >> request_id;
        }
        return members;
    }

    void read_task_completion() {
        string server;
        string family;
        string step;
        cin >> server >> family >> step;
        free_server(server);

        double duration = 0;

        if (family == "P" && step == "PRE") {
            int cloud = 0;
            int request_id = 0;
            cin >> cloud >> request_id >> duration;
            Request& req = request(request_id);
            expect_state(req, RequestState::P_PRE_RUNNING, "P PRE TDN");
            if (req.cloud != cloud) {
                fail("P PRE TDN echoed the wrong cloud");
            }
            req.state = RequestState::WAITING_PREFILL_UP;
            return;
        }

        if (family == "P" && step == "PROC") {
            int layer_start = 0;
            int layer_end = 0;
            int cloud = 0;
            int request_id = 0;
            cin >> layer_start >> layer_end >> cloud >> request_id >> duration;
            Request& req = request(request_id);
            expect_state(req, RequestState::P_PROC_RUNNING, "P PROC TDN");
            if (req.cloud != cloud || layer_start != 0 || layer_end != layer_count_) {
                fail("P PROC TDN did not match the full-piece baseline task");
            }
            req.state = RequestState::WAITING_PREFILL_DOWN;
            return;
        }

        if (family == "P" && step == "POST") {
            int cloud = 0;
            int request_id = 0;
            cin >> cloud >> request_id >> duration;
            Request& req = request(request_id);
            expect_state(req, RequestState::P_POST_RUNNING, "P POST TDN");
            if (req.cloud != cloud) {
                fail("P POST TDN echoed the wrong cloud");
            }
            req.state = RequestState::D_PRE_READY;
            enqueue_edge(TaskKind::D_PRE, request_id);
            return;
        }

        if (family == "D" && step == "PRE") {
            int marker = 0;
            int member_count = 0;
            cin >> marker >> member_count;
            vector<int> members = read_group_members(member_count);
            cin >> duration;
            if (marker != -1) {
                fail("D PRE TDN had a non--1 marker");
            }
            for (int request_id : members) {
                Request& req = request(request_id);
                expect_state(req, RequestState::D_PRE_RUNNING, "D PRE TDN");
                req.state = RequestState::WAITING_DECODE_UP;
            }
            return;
        }

        if (family == "D" && step == "PROC") {
            int cloud = 0;
            int member_count = 0;
            cin >> cloud >> member_count;
            vector<int> members = read_group_members(member_count);
            cin >> duration;
            for (int request_id : members) {
                Request& req = request(request_id);
                expect_state(req, RequestState::D_PROC_RUNNING, "D PROC TDN");
                if (req.cloud != cloud) {
                    fail("D PROC TDN echoed the wrong cloud");
                }
                req.state = RequestState::WAITING_DECODE_DOWN;
            }
            return;
        }

        if (family == "D" && step == "POST") {
            int marker = 0;
            int member_count = 0;
            cin >> marker >> member_count;
            vector<int> members = read_group_members(member_count);
            cin >> duration;
            if (marker != -1) {
                fail("D POST TDN had a non--1 marker");
            }
            for (int request_id : members) {
                Request& req = request(request_id);
                // FIN and the final D POST TDN share a frame, but their line order is not
                // semantically significant. FIN may therefore have marked the request first.
                if (req.state != RequestState::D_POST_RUNNING &&
                    req.state != RequestState::FINISHED) {
                    fail("D POST TDN arrived while request " + to_string(req.id) +
                         " was in an unexpected state");
                }
                d_post_completed_this_frame_.push_back(request_id);
            }
            return;
        }

        fail("unknown completed task: " + family + " " + step);
    }

    void read_transfer_completion() {
        string direction;
        int cloud = 0;
        long long size_bytes = 0;
        string phase;
        int member_count = 0;
        cin >> direction >> cloud >> size_bytes >> phase >> member_count;
        vector<int> members = read_group_members(member_count);

        (void)size_bytes;

        for (int request_id : members) {
            Request& req = request(request_id);
            if (req.cloud != cloud) {
                fail("XDN delivered request to the wrong cloud");
            }

            if (phase == "PRE" && direction == "UP") {
                expect_state(req, RequestState::WAITING_PREFILL_UP, "prefill UP XDN");
                req.state = RequestState::P_PROC_READY;
                enqueue_cloud(TaskKind::P_PROC, cloud, request_id);
            } else if (phase == "PRE" && direction == "DOWN") {
                expect_state(req, RequestState::WAITING_PREFILL_DOWN, "prefill DOWN XDN");
                req.state = RequestState::P_POST_READY;
                enqueue_edge(TaskKind::P_POST, request_id);
            } else if (phase == "DEC" && direction == "UP") {
                expect_state(req, RequestState::WAITING_DECODE_UP, "decode UP XDN");
                req.state = RequestState::D_PROC_READY;
                enqueue_cloud(TaskKind::D_PROC, cloud, request_id);
            } else if (phase == "DEC" && direction == "DOWN") {
                expect_state(req, RequestState::WAITING_DECODE_DOWN, "decode DOWN XDN");
                req.state = RequestState::D_POST_READY;
                enqueue_edge(TaskKind::D_POST, request_id);
            } else {
                fail("invalid XDN direction/phase pair: " + direction + " " + phase);
            }
        }
    }

    void read_finish() {
        int request_id = 0;
        cin >> request_id;
        Request& req = request(request_id);
        if (req.state != RequestState::D_POST_RUNNING) {
            fail("FIN arrived outside a D POST completion frame");
        }

        int cloud = req.cloud;
        if (cloud < 0 || cloud >= cloud_count_ || !cloud_reserved_[cloud]) {
            fail("FIN attempted to release an unreserved cloud");
        }

        req.state = RequestState::FINISHED;
        cloud_reserved_[cloud] = false;
        free_clouds_.push_back(cloud);
    }

    void finalize_decode_completions() {
        // FIN is guaranteed to share the final D POST's frame, but event-line order has no
        // priority. Deferring this transition prevents us from re-enqueueing a finished request.
        for (int request_id : d_post_completed_this_frame_) {
            Request& req = request(request_id);
            if (req.state == RequestState::FINISHED) {
                continue;
            }
            expect_state(req, RequestState::D_POST_RUNNING, "non-final D POST completion");
            req.state = RequestState::D_PRE_READY;
            enqueue_edge(TaskKind::D_PRE, request_id);
        }
    }

    string dispatch_admission() {
        int request_id = pending_requests_.front();
        pending_requests_.pop_front();

        int cloud = free_clouds_.front();
        free_clouds_.pop_front();

        Request& req = request(request_id);
        expect_state(req, RequestState::WAITING_FOR_CLOUD, "P PRE dispatch");
        if (cloud_reserved_[cloud]) {
            fail("admission selected a reserved cloud");
        }

        req.cloud = cloud;
        req.state = RequestState::P_PRE_RUNNING;
        cloud_reserved_[cloud] = true;
        edge_busy_ = true;

        return "E P PRE " + to_string(cloud) + " " + to_string(request_id);
    }

    string dispatch_edge_task() {
        ReadyTask task = edge_ready_.front();
        edge_ready_.pop_front();
        Request& req = request(task.request_id);

        edge_busy_ = true;
        switch (task.kind) {
            case TaskKind::P_POST:
                expect_state(req, RequestState::P_POST_READY, "P POST dispatch");
                req.state = RequestState::P_POST_RUNNING;
                return "E P POST " + to_string(req.cloud) + " " + to_string(req.id);
            case TaskKind::D_PRE:
                expect_state(req, RequestState::D_PRE_READY, "D PRE dispatch");
                req.state = RequestState::D_PRE_RUNNING;
                return "E D PRE -1 1 " + to_string(req.id);
            case TaskKind::D_POST:
                expect_state(req, RequestState::D_POST_READY, "D POST dispatch");
                req.state = RequestState::D_POST_RUNNING;
                return "E D POST -1 1 " + to_string(req.id);
            case TaskKind::P_PROC:
            case TaskKind::D_PROC:
                fail("cloud task appeared in the edge queue");
        }
        fail("unreachable edge task kind");
    }

    string dispatch_cloud_task(int cloud) {
        ReadyTask task = cloud_ready_[cloud].front();
        cloud_ready_[cloud].pop_front();
        Request& req = request(task.request_id);

        if (!cloud_reserved_[cloud] || req.cloud != cloud) {
            fail("cloud task did not belong to the cloud's reserved request");
        }

        cloud_busy_[cloud] = true;
        switch (task.kind) {
            case TaskKind::P_PROC:
                expect_state(req, RequestState::P_PROC_READY, "P PROC dispatch");
                req.state = RequestState::P_PROC_RUNNING;
                return "C" + to_string(cloud) + " P PROC 0 " + to_string(layer_count_) +
                       " " + to_string(cloud) + " " + to_string(req.id);
            case TaskKind::D_PROC:
                expect_state(req, RequestState::D_PROC_READY, "D PROC dispatch");
                req.state = RequestState::D_PROC_RUNNING;
                return "C" + to_string(cloud) + " D PROC " + to_string(cloud) + " 1 " +
                       to_string(req.id);
            case TaskKind::P_POST:
            case TaskKind::D_PRE:
            case TaskKind::D_POST:
                fail("edge task appeared in a cloud queue");
        }
        fail("unreachable cloud task kind");
    }

    vector<string> dispatch_ready_work() {
        vector<string> assignments;
        assignments.reserve(cloud_count_ + 1);

        if (!edge_busy_) {
            const bool admission_available =
                !pending_requests_.empty() && !free_clouds_.empty();
            const bool edge_task_available = !edge_ready_.empty();

            if (admission_available || edge_task_available) {
                bool choose_admission = false;
                if (!edge_task_available) {
                    choose_admission = true;
                } else if (admission_available) {
                    const Request& pending = request(pending_requests_.front());
                    choose_admission =
                        pending.admission_sequence <= edge_ready_.front().sequence;
                }

                if (choose_admission) {
                    assignments.push_back(dispatch_admission());
                } else {
                    assignments.push_back(dispatch_edge_task());
                }
            }
        }

        for (int cloud = 0; cloud < cloud_count_; ++cloud) {
            if (!cloud_busy_[cloud] && !cloud_ready_[cloud].empty()) {
                assignments.push_back(dispatch_cloud_task(cloud));
            }
        }

        if (assignments.size() > static_cast<size_t>(cloud_count_ + 1)) {
            fail("attempted too many assignments in one response");
        }
        return assignments;
    }

    void print_response(const vector<string>& assignments) const {
        cout << assignments.size() << '\n';
        for (const string& assignment : assignments) {
            cout << assignment << '\n';
        }
        cout << flush;
    }
};

}  // namespace

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    BaselineScheduler scheduler;
    if (!scheduler.read_startup()) {
        return 0;
    }
    scheduler.run();
    return 0;
}
