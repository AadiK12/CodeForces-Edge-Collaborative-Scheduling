#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <limits>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using namespace std;

#ifndef OPT_LEVEL
#define OPT_LEVEL 7
#endif

static_assert(1 <= OPT_LEVEL && OPT_LEVEL <= 7, "OPT_LEVEL must be in [1, 7]");

namespace {

constexpr int kOptimizationLevel = OPT_LEVEL;

enum class RequestState {
    UNSEEN,
    READY_P_PRE,
    RUNNING_P_PRE,
    WAITING_PREFILL_UP,
    READY_P_PROC,
    RUNNING_P_PROC,
    WAITING_PREFILL_DOWN,
    READY_P_POST,
    RUNNING_P_POST,
    READY_D_PRE,
    RUNNING_D_PRE,
    WAITING_DECODE_UP,
    READY_D_PROC,
    RUNNING_D_PROC,
    WAITING_DECODE_DOWN,
    READY_D_POST,
    RUNNING_D_POST,
    FINISHED,
};

enum class TaskKind {
    P_PRE,
    P_POST,
    D_PRE,
    D_POST,
    P_PROC,
    D_PROC,
};

enum class DurationColumn {
    PREFILL_PRE = 0,
    PREFILL_PROC = 1,
    PREFILL_POST = 2,
    DECODE_PRE = 3,
    DECODE_PROC = 4,
    DECODE_POST = 5,
};

struct Request {
    int id = -1;
    int input_length = 0;
    int cloud = -1;
    int next_prefill_layer = 0;
    RequestState state = RequestState::UNSEEN;
    uint64_t ready_sequence = 0;
    double arrival_time = 0;
    double ready_time = 0;
    double decode_clock_start = 0;
};

struct Candidate {
    TaskKind kind;
    int request_id;
    uint64_t sequence;
    double urgency;
    int stage_rank;
};

class LayeredScheduler {
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
        array<vector<pair<int, double>>, 6> raw_curves;
        for (int row = 0; row < row_count; ++row) {
            int size = 0;
            array<double, 6> values{};
            cin >> size;
            for (double& value : values) {
                cin >> value;
            }
            for (int column = 0; column < 6; ++column) {
                if (values[column] >= 0) {
                    raw_curves[column].push_back({size, values[column]});
                }
            }
        }
        for (int column = 0; column < 6; ++column) {
            if (raw_curves[column].empty()) {
                fail("task-time column has no usable values");
            }
            sort(raw_curves[column].begin(), raw_curves[column].end());
            duration_curves_[column] = std::move(raw_curves[column]);
        }

        cloud_busy_.assign(cloud_count_, false);
        cloud_busy_until_.assign(cloud_count_, 0);
        active_requests_.assign(cloud_count_, 0);
        active_decode_requests_.assign(cloud_count_, 0);
        pending_prefill_work_.assign(cloud_count_, 0);
        p_proc_ready_.resize(cloud_count_);
        d_proc_ready_.resize(cloud_count_);
        return true;
    }

    void run() {
        string frame_header;
        while (cin >> frame_header) {
            if (frame_header == "END") {
                return;
            }
            current_time_ = stod(frame_header);
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

    double current_time_ = 0;
    double edge_busy_until_ = 0;
    uint64_t next_ready_sequence_ = 0;
    int next_round_robin_cloud_ = 0;

    array<vector<pair<int, double>>, 6> duration_curves_;
    vector<Request> requests_;

    bool edge_busy_ = false;
    vector<bool> cloud_busy_;
    vector<double> cloud_busy_until_;
    vector<int> active_requests_;
    vector<int> active_decode_requests_;
    int total_active_decode_requests_ = 0;
    vector<double> pending_prefill_work_;

    int pending_up_transfers_ = 0;
    int pending_down_transfers_ = 0;
    long long pending_up_bytes_ = 0;
    long long pending_down_bytes_ = 0;

    deque<int> p_pre_ready_;
    deque<int> p_post_ready_;
    deque<int> d_pre_ready_;
    deque<int> d_post_ready_;
    vector<deque<int>> p_proc_ready_;
    vector<deque<int>> d_proc_ready_;
    vector<int> d_post_completed_this_frame_;

    [[noreturn]] void fail(const string& message) const {
        cerr << "layered scheduler error at t=" << current_time_ << ": " << message << '\n';
        exit(0);
    }

    Request& request(int request_id) {
        if (request_id < 0 || request_id >= static_cast<int>(requests_.size()) ||
            requests_[request_id].state == RequestState::UNSEEN) {
            fail("unknown request " + to_string(request_id));
        }
        return requests_[request_id];
    }

    const Request& request(int request_id) const {
        if (request_id < 0 || request_id >= static_cast<int>(requests_.size()) ||
            requests_[request_id].state == RequestState::UNSEEN) {
            fail("unknown request " + to_string(request_id));
        }
        return requests_[request_id];
    }

    void expect_state(const Request& req, RequestState expected, const string& action) const {
        if (req.state != expected) {
            fail(action + " found request " + to_string(req.id) + " in the wrong state");
        }
    }

    uint64_t new_sequence() {
        return ++next_ready_sequence_;
    }

    void mark_ready(Request& req, RequestState state, deque<int>& queue) {
        req.state = state;
        req.ready_sequence = new_sequence();
        req.ready_time = current_time_;
        queue.push_back(req.id);
    }

    void mark_cloud_ready(Request& req, RequestState state, vector<deque<int>>& queues) {
        if (req.cloud < 0 || req.cloud >= cloud_count_) {
            fail("ready cloud task has no valid cloud");
        }
        req.state = state;
        req.ready_sequence = new_sequence();
        req.ready_time = current_time_;
        queues[req.cloud].push_back(req.id);
    }

    double duration(DurationColumn column, int size) const {
        const vector<pair<int, double>>& points = duration_curves_[static_cast<int>(column)];
        if (size <= points.front().first) {
            return points.front().second;
        }
        if (size >= points.back().first) {
            return points.back().second;
        }
        auto right = lower_bound(
            points.begin(), points.end(), make_pair(size, -numeric_limits<double>::infinity())
        );
        if (right != points.end() && right->first == size) {
            return right->second;
        }
        auto left = prev(right);
        const double fraction =
            static_cast<double>(size - left->first) / (right->first - left->first);
        return left->second + fraction * (right->second - left->second);
    }

    double transfer_time(long long size_bytes, int transfer_count = 1) const {
        return transfer_count * latency_ms_ +
               8.0 * static_cast<double>(size_bytes) / (bandwidth_gbps_ * 1'000'000.0);
    }

    void add_transfer(const string& direction, long long size_bytes, int count = 1) {
        if (direction == "UP") {
            pending_up_transfers_ += count;
            pending_up_bytes_ += size_bytes;
        } else if (direction == "DOWN") {
            pending_down_transfers_ += count;
            pending_down_bytes_ += size_bytes;
        } else {
            fail("invalid transfer direction");
        }
    }

    void complete_transfer(const string& direction, long long size_bytes) {
        if (direction == "UP") {
            if (pending_up_transfers_ <= 0 || pending_up_bytes_ < size_bytes) {
                fail("UP transfer accounting underflow");
            }
            --pending_up_transfers_;
            pending_up_bytes_ -= size_bytes;
        } else if (direction == "DOWN") {
            if (pending_down_transfers_ <= 0 || pending_down_bytes_ < size_bytes) {
                fail("DOWN transfer accounting underflow");
            }
            --pending_down_transfers_;
            pending_down_bytes_ -= size_bytes;
        } else {
            fail("invalid completed transfer direction");
        }
    }

    bool has_known_future_event() const {
        if (edge_busy_ || pending_up_transfers_ > 0 || pending_down_transfers_ > 0) {
            return true;
        }
        return any_of(cloud_busy_.begin(), cloud_busy_.end(), [](bool busy) { return busy; });
    }

    void read_arrival() {
        int request_id = 0;
        int input_length = 0;
        cin >> request_id >> input_length;
        if (request_id >= static_cast<int>(requests_.size())) {
            requests_.resize(request_id + 1);
        }
        if (requests_[request_id].state != RequestState::UNSEEN) {
            fail("duplicate ARR");
        }
        Request& req = requests_[request_id];
        req.id = request_id;
        req.input_length = input_length;
        req.arrival_time = current_time_;
        req.cloud = -1;
        req.next_prefill_layer = 0;
        mark_ready(req, RequestState::READY_P_PRE, p_pre_ready_);
    }

    int cloud_from_server(const string& server) const {
        if (server.size() < 2 || server.front() != 'C') {
            fail("invalid cloud server " + server);
        }
        const int cloud = stoi(server.substr(1));
        if (cloud < 0 || cloud >= cloud_count_) {
            fail("cloud server out of range");
        }
        return cloud;
    }

    void free_server(const string& server) {
        if (server == "E") {
            if (!edge_busy_) {
                fail("TDN attempted to free an idle edge");
            }
            edge_busy_ = false;
            edge_busy_until_ = current_time_;
            return;
        }
        const int cloud = cloud_from_server(server);
        if (!cloud_busy_[cloud]) {
            fail("TDN attempted to free an idle cloud");
        }
        cloud_busy_[cloud] = false;
        cloud_busy_until_[cloud] = current_time_;
    }

    vector<int> read_members(int member_count) {
        if (member_count < 1) {
            fail("empty group in event");
        }
        vector<int> members(member_count);
        for (int& member : members) {
            cin >> member;
        }
        return members;
    }

    void read_task_completion() {
        string server;
        string family;
        string step;
        cin >> server >> family >> step;
        free_server(server);
        double task_duration = 0;

        if (family == "P" && step == "PRE") {
            int cloud = 0;
            int request_id = 0;
            cin >> cloud >> request_id >> task_duration;
            Request& req = request(request_id);
            expect_state(req, RequestState::RUNNING_P_PRE, "P PRE TDN");
            if (req.cloud != cloud) {
                fail("P PRE TDN echoed the wrong cloud");
            }
            req.state = RequestState::WAITING_PREFILL_UP;
            add_transfer("UP", static_cast<long long>(req.input_length) * bytes_per_token_);
            return;
        }

        if (family == "P" && step == "PROC") {
            int layer_start = 0;
            int layer_end = 0;
            int cloud = 0;
            int request_id = 0;
            cin >> layer_start >> layer_end >> cloud >> request_id >> task_duration;
            Request& req = request(request_id);
            expect_state(req, RequestState::RUNNING_P_PROC, "P PROC TDN");
            if (req.cloud != cloud || layer_start != req.next_prefill_layer ||
                layer_end <= layer_start || layer_end > layer_count_) {
                fail("P PROC TDN did not match the dispatched piece");
            }
            req.next_prefill_layer = layer_end;
            if (layer_end == layer_count_) {
                req.state = RequestState::WAITING_PREFILL_DOWN;
                add_transfer(
                    "DOWN", static_cast<long long>(req.input_length) * bytes_per_token_
                );
            } else {
                mark_cloud_ready(req, RequestState::READY_P_PROC, p_proc_ready_);
            }
            return;
        }

        if (family == "P" && step == "POST") {
            int cloud = 0;
            int request_id = 0;
            cin >> cloud >> request_id >> task_duration;
            Request& req = request(request_id);
            expect_state(req, RequestState::RUNNING_P_POST, "P POST TDN");
            if (req.cloud != cloud) {
                fail("P POST TDN echoed the wrong cloud");
            }
            ++active_decode_requests_[cloud];
            ++total_active_decode_requests_;
            req.decode_clock_start = current_time_;
            mark_ready(req, RequestState::READY_D_PRE, d_pre_ready_);
            return;
        }

        if (family == "D" && step == "PRE") {
            int marker = 0;
            int member_count = 0;
            cin >> marker >> member_count;
            vector<int> members = read_members(member_count);
            cin >> task_duration;
            if (marker != -1) {
                fail("D PRE TDN marker was not -1");
            }
            set<int> represented_clouds;
            for (int request_id : members) {
                Request& req = request(request_id);
                expect_state(req, RequestState::RUNNING_D_PRE, "D PRE TDN");
                req.state = RequestState::WAITING_DECODE_UP;
                represented_clouds.insert(req.cloud);
            }
            add_transfer(
                "UP",
                static_cast<long long>(members.size()) * bytes_per_token_,
                static_cast<int>(represented_clouds.size())
            );
            return;
        }

        if (family == "D" && step == "PROC") {
            int cloud = 0;
            int member_count = 0;
            cin >> cloud >> member_count;
            vector<int> members = read_members(member_count);
            cin >> task_duration;
            for (int request_id : members) {
                Request& req = request(request_id);
                expect_state(req, RequestState::RUNNING_D_PROC, "D PROC TDN");
                if (req.cloud != cloud) {
                    fail("D PROC TDN echoed the wrong cloud");
                }
                req.state = RequestState::WAITING_DECODE_DOWN;
            }
            add_transfer("DOWN", static_cast<long long>(members.size()) * bytes_per_token_);
            return;
        }

        if (family == "D" && step == "POST") {
            int marker = 0;
            int member_count = 0;
            cin >> marker >> member_count;
            vector<int> members = read_members(member_count);
            cin >> task_duration;
            if (marker != -1) {
                fail("D POST TDN marker was not -1");
            }
            for (int request_id : members) {
                Request& req = request(request_id);
                if (req.state != RequestState::RUNNING_D_POST &&
                    req.state != RequestState::FINISHED) {
                    fail("D POST TDN found a request in the wrong state");
                }
                d_post_completed_this_frame_.push_back(request_id);
            }
            return;
        }

        fail("unknown completed task");
    }

    void read_transfer_completion() {
        string direction;
        int cloud = 0;
        long long size_bytes = 0;
        string phase;
        int member_count = 0;
        cin >> direction >> cloud >> size_bytes >> phase >> member_count;
        vector<int> members = read_members(member_count);
        complete_transfer(direction, size_bytes);

        for (int request_id : members) {
            Request& req = request(request_id);
            if (req.cloud != cloud) {
                fail("XDN delivered a request to the wrong cloud");
            }
            if (phase == "PRE" && direction == "UP") {
                expect_state(req, RequestState::WAITING_PREFILL_UP, "prefill UP XDN");
                mark_cloud_ready(req, RequestState::READY_P_PROC, p_proc_ready_);
            } else if (phase == "PRE" && direction == "DOWN") {
                expect_state(req, RequestState::WAITING_PREFILL_DOWN, "prefill DOWN XDN");
                mark_ready(req, RequestState::READY_P_POST, p_post_ready_);
            } else if (phase == "DEC" && direction == "UP") {
                expect_state(req, RequestState::WAITING_DECODE_UP, "decode UP XDN");
                mark_cloud_ready(req, RequestState::READY_D_PROC, d_proc_ready_);
            } else if (phase == "DEC" && direction == "DOWN") {
                expect_state(req, RequestState::WAITING_DECODE_DOWN, "decode DOWN XDN");
                mark_ready(req, RequestState::READY_D_POST, d_post_ready_);
            } else {
                fail("invalid XDN direction and phase");
            }
        }
    }

    void read_finish() {
        int request_id = 0;
        cin >> request_id;
        Request& req = request(request_id);
        if (req.state != RequestState::RUNNING_D_POST) {
            fail("FIN arrived outside a D POST completion frame");
        }
        req.state = RequestState::FINISHED;
        if (req.cloud < 0 || active_requests_[req.cloud] <= 0 ||
            active_decode_requests_[req.cloud] <= 0 || total_active_decode_requests_ <= 0) {
            fail("FIN request counters underflowed");
        }
        --active_requests_[req.cloud];
        --active_decode_requests_[req.cloud];
        --total_active_decode_requests_;
    }

    void finalize_decode_completions() {
        for (int request_id : d_post_completed_this_frame_) {
            Request& req = request(request_id);
            if (req.state == RequestState::FINISHED) {
                continue;
            }
            expect_state(req, RequestState::RUNNING_D_POST, "non-final D POST completion");
            req.decode_clock_start = current_time_;
            mark_ready(req, RequestState::READY_D_PRE, d_pre_ready_);
        }
    }

    void clean_front(deque<int>& queue, RequestState expected) {
        while (!queue.empty() && request(queue.front()).state != expected) {
            queue.pop_front();
        }
    }

    bool queue_available(deque<int>& queue, RequestState expected) {
        clean_front(queue, expected);
        return !queue.empty();
    }

    int queue_front(deque<int>& queue, RequestState expected) {
        if (!queue_available(queue, expected)) {
            fail("attempted to read an empty ready queue");
        }
        return queue.front();
    }

    vector<int> take_front(deque<int>& queue, RequestState expected, int count) {
        vector<int> members;
        members.reserve(count);
        while (static_cast<int>(members.size()) < count) {
            clean_front(queue, expected);
            if (queue.empty()) {
                fail("ready queue contained fewer members than expected");
            }
            const int request_id = queue.front();
            queue.pop_front();
            members.push_back(request_id);
        }
        return members;
    }

    int take_link_aware_prefill_request() {
        clean_front(p_pre_ready_, RequestState::READY_P_PRE);
        if (p_pre_ready_.empty()) {
            fail("link-aware admission read an empty queue");
        }
        if constexpr (kOptimizationLevel < 7) {
            const int request_id = p_pre_ready_.front();
            p_pre_ready_.pop_front();
            return request_id;
        }
        if (latency_weight_ <= throughput_weight_) {
            const int request_id = p_pre_ready_.front();
            p_pre_ready_.pop_front();
            return request_id;
        }

        const int window = min<int>(64, p_pre_ready_.size());
        int best_index = 0;
        double best_score = numeric_limits<double>::infinity();
        for (int index = 0; index < window; ++index) {
            const Request& req = request(p_pre_ready_[index]);
            const double age_ratio = (current_time_ - req.arrival_time) / max(1e-9, slo_tdr_);
            const double transfer = transfer_time(
                static_cast<long long>(req.input_length) * bytes_per_token_
            );
            const double score = transfer - age_ratio * slo_tdr_ * 0.5;
            if (score < best_score) {
                best_score = score;
                best_index = index;
            }
        }
        const int request_id = p_pre_ready_[best_index];
        p_pre_ready_.erase(p_pre_ready_.begin() + best_index);
        return request_id;
    }

    double cloud_load_score(int cloud) const {
        const double remaining_busy = max(0.0, cloud_busy_until_[cloud] - current_time_);
        const double decode_proxy =
            active_requests_[cloud] * (schedule_cost_ + duration(DurationColumn::DECODE_PROC, 1));
        const int ready_decode = static_cast<int>(d_proc_ready_[cloud].size());
        const double ready_decode_work =
            ready_decode > 0
                ? schedule_cost_ + duration(DurationColumn::DECODE_PROC, ready_decode)
                : 0.0;
        return remaining_busy + pending_prefill_work_[cloud] + ready_decode_work +
               0.35 * decode_proxy;
    }

    int choose_cloud() {
        if constexpr (kOptimizationLevel == 1) {
            const int cloud = next_round_robin_cloud_;
            next_round_robin_cloud_ = (next_round_robin_cloud_ + 1) % cloud_count_;
            return cloud;
        }

        int best_cloud = 0;
        double best_load = cloud_load_score(0);
        for (int cloud = 1; cloud < cloud_count_; ++cloud) {
            const double load = cloud_load_score(cloud);
            if (load + 1e-12 < best_load) {
                best_load = load;
                best_cloud = cloud;
            }
        }
        return best_cloud;
    }

    double request_urgency(TaskKind kind, const Request& req) const {
        if (kind == TaskKind::P_PRE || kind == TaskKind::P_POST || kind == TaskKind::P_PROC) {
            return (current_time_ - req.arrival_time) / max(1e-9, slo_tdr_);
        }
        return (current_time_ - req.decode_clock_start) / max(1e-9, slo_tpot_);
    }

    int edge_stage_rank(TaskKind kind) const {
        switch (kind) {
            case TaskKind::D_POST:
                return 0;
            case TaskKind::P_POST:
                return 1;
            case TaskKind::D_PRE:
                return 2;
            case TaskKind::P_PRE:
                return 3;
            case TaskKind::P_PROC:
            case TaskKind::D_PROC:
                break;
        }
        return 4;
    }

    vector<Candidate> edge_candidates() {
        vector<Candidate> candidates;
        auto add = [&](TaskKind kind, deque<int>& queue, RequestState expected) {
            if (!queue_available(queue, expected)) {
                return;
            }
            const int request_id = queue.front();
            const Request& req = request(request_id);
            candidates.push_back(
                {kind, request_id, req.ready_sequence, request_urgency(kind, req),
                 edge_stage_rank(kind)}
            );
        };
        add(TaskKind::P_PRE, p_pre_ready_, RequestState::READY_P_PRE);
        add(TaskKind::P_POST, p_post_ready_, RequestState::READY_P_POST);
        add(TaskKind::D_PRE, d_pre_ready_, RequestState::READY_D_PRE);
        add(TaskKind::D_POST, d_post_ready_, RequestState::READY_D_POST);

        if constexpr (kOptimizationLevel < 5) {
            sort(candidates.begin(), candidates.end(), [](const Candidate& left, const Candidate& right) {
                if (left.sequence != right.sequence) {
                    return left.sequence < right.sequence;
                }
                return left.stage_rank < right.stage_rank;
            });
        } else {
            sort(candidates.begin(), candidates.end(), [this](const Candidate& left, const Candidate& right) {
                const bool left_overdue = latency_weight_ > 0.8 && left.urgency >= 1.0;
                const bool right_overdue = latency_weight_ > 0.8 && right.urgency >= 1.0;
                if (left_overdue != right_overdue) {
                    return left_overdue;
                }
                if (left_overdue) {
                    const double left_priority = left.urgency + 0.1 * (3 - left.stage_rank);
                    const double right_priority = right.urgency + 0.1 * (3 - right.stage_rank);
                    if (abs(left_priority - right_priority) > 1e-12) {
                        return left_priority > right_priority;
                    }
                }
                if (left.sequence != right.sequence) {
                    return left.sequence < right.sequence;
                }
                return left.stage_rank < right.stage_rank;
            });
        }
        if constexpr (kOptimizationLevel >= 7) {
            bool link_constrained = bandwidth_gbps_ < 0.1;
            if (queue_available(p_pre_ready_, RequestState::READY_P_PRE)) {
                const Request& pending_prefill = request(p_pre_ready_.front());
                link_constrained = link_constrained ||
                    transfer_time(
                        static_cast<long long>(pending_prefill.input_length) * bytes_per_token_
                    ) > slo_tpot_;
            }
            if (link_constrained) {
                stable_sort(
                    candidates.begin(),
                    candidates.end(),
                    [](const Candidate& left, const Candidate& right) {
                        return left.stage_rank < right.stage_rank;
                    }
                );
            }
        }
        return candidates;
    }

    int best_group_size(DurationColumn column, int available) const {
        if (available <= 1 || kOptimizationLevel < 3) {
            return 1;
        }
        if constexpr (kOptimizationLevel == 3) {
            return available;
        }

        set<int> candidates = {1, available};
        for (const auto& [size, ignored] : duration_curves_[static_cast<int>(column)]) {
            (void)ignored;
            for (int candidate : {size - 1, size, size + 1}) {
                if (1 <= candidate && candidate <= available) {
                    candidates.insert(candidate);
                }
            }
        }

        int best_size = 1;
        double best_rate = -1;
        for (int size : candidates) {
            double service_time = schedule_cost_ + duration(column, size);
            if constexpr (kOptimizationLevel >= 7) {
                if (column == DurationColumn::DECODE_PRE ||
                    column == DurationColumn::DECODE_PROC) {
                    service_time += transfer_time(
                        static_cast<long long>(size) * bytes_per_token_
                    );
                }
            }
            const double rate = size / service_time;
            if (rate > best_rate + 1e-12 ||
                (abs(rate - best_rate) <= 1e-12 && size < best_size)) {
                best_rate = rate;
                best_size = size;
            }
        }
        return best_size;
    }

    bool should_wait_for_group(
        TaskKind kind,
        DurationColumn column,
        int cloud,
        int available,
        double oldest_ready_time,
        bool allow_wait
    ) const {
        if constexpr (kOptimizationLevel < 5) {
            return false;
        }
        if (!allow_wait || kind == TaskKind::D_POST || available <= 0) {
            return false;
        }
        // Waiting has no self-wake timer and easily overshoots on sparse streams. Restrict it
        // to tests that are almost purely throughput-weighted; the urgency guard below still
        // prevents waiting once a member consumes half of its TPOT budget.
        if (throughput_weight_ < 0.95) {
            return false;
        }
        int possible = total_active_decode_requests_;
        if (kind == TaskKind::D_PROC) {
            possible = active_decode_requests_[cloud];
        }
        possible = max(possible, available);
        const int target = best_group_size(column, possible);
        if (available >= target) {
            return false;
        }
        const Request& oldest = request(
            kind == TaskKind::D_PROC ? d_proc_ready_[cloud].front() : d_pre_ready_.front()
        );
        if (request_urgency(kind, oldest) >= 0.5) {
            return false;
        }
        const double wait_budget = slo_tpot_ * (0.02 + 0.18 * throughput_weight_);
        const double waited = current_time_ - oldest_ready_time;
        return waited + 1e-12 < wait_budget && has_known_future_event();
    }

    bool should_defer_prefill_admission(const Request& req, bool allow_wait) const {
        if constexpr (kOptimizationLevel < 7) {
            return false;
        }
        if (!allow_wait || pending_up_transfers_ == 0 || !has_known_future_event()) {
            return false;
        }
        const double pressure = transfer_time(pending_up_bytes_, pending_up_transfers_);
        const double age = current_time_ - req.arrival_time;
        if (latency_weight_ < 0.8) {
            return false;
        }
        // Never hold admission for a large fraction of SLO1: without a timer, one deferral can
        // last until a much later transfer. This narrow guard only avoids adding another large
        // prefill behind an already extreme UP backlog.
        return pressure > slo_tdr_ && age < 0.05 * slo_tdr_;
    }

    string join_members(const vector<int>& members) const {
        ostringstream output;
        for (int request_id : members) {
            output << ' ' << request_id;
        }
        return output.str();
    }

    optional<string> dispatch_edge(bool allow_wait) {
        if (edge_busy_) {
            return nullopt;
        }
        vector<Candidate> candidates = edge_candidates();
        for (const Candidate& candidate : candidates) {
            if (candidate.kind == TaskKind::P_PRE) {
                const Request& front = request(queue_front(p_pre_ready_, RequestState::READY_P_PRE));
                if (should_defer_prefill_admission(front, allow_wait)) {
                    continue;
                }
                const int request_id = take_link_aware_prefill_request();
                Request& req = request(request_id);
                expect_state(req, RequestState::READY_P_PRE, "P PRE dispatch");
                const int cloud = choose_cloud();
                req.cloud = cloud;
                req.state = RequestState::RUNNING_P_PRE;
                ++active_requests_[cloud];
                pending_prefill_work_[cloud] += duration(DurationColumn::PREFILL_PROC, req.input_length);
                edge_busy_ = true;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::PREFILL_PRE, req.input_length);
                return "E P PRE " + to_string(cloud) + " " + to_string(request_id);
            }

            if (candidate.kind == TaskKind::P_POST) {
                const int request_id = take_front(
                    p_post_ready_, RequestState::READY_P_POST, 1
                ).front();
                Request& req = request(request_id);
                req.state = RequestState::RUNNING_P_POST;
                edge_busy_ = true;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::PREFILL_POST, req.input_length);
                return "E P POST " + to_string(req.cloud) + " " + to_string(request_id);
            }

            if (candidate.kind == TaskKind::D_PRE) {
                const int available = static_cast<int>(d_pre_ready_.size());
                const int oldest = queue_front(d_pre_ready_, RequestState::READY_D_PRE);
                if (should_wait_for_group(
                        TaskKind::D_PRE,
                        DurationColumn::DECODE_PRE,
                        -1,
                        available,
                        request(oldest).ready_time,
                        allow_wait
                    )) {
                    continue;
                }
                const int group_size = best_group_size(DurationColumn::DECODE_PRE, available);
                vector<int> members = take_front(
                    d_pre_ready_, RequestState::READY_D_PRE, group_size
                );
                for (int request_id : members) {
                    request(request_id).state = RequestState::RUNNING_D_PRE;
                }
                edge_busy_ = true;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::DECODE_PRE, group_size);
                return "E D PRE -1 " + to_string(group_size) + join_members(members);
            }

            if (candidate.kind == TaskKind::D_POST) {
                const int available = static_cast<int>(d_post_ready_.size());
                const int group_size = best_group_size(DurationColumn::DECODE_POST, available);
                vector<int> members = take_front(
                    d_post_ready_, RequestState::READY_D_POST, group_size
                );
                for (int request_id : members) {
                    request(request_id).state = RequestState::RUNNING_D_POST;
                }
                edge_busy_ = true;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::DECODE_POST, group_size);
                return "E D POST -1 " + to_string(group_size) + join_members(members);
            }
        }
        return nullopt;
    }

    int choose_prefill_piece_end(const Request& req, int cloud) const {
        if constexpr (kOptimizationLevel < 6) {
            return layer_count_;
        }
        const int remaining_layers = layer_count_ - req.next_prefill_layer;
        if (remaining_layers <= 1 || layer_count_ <= 8) {
            return layer_count_;
        }
        const double full_duration = duration(DurationColumn::PREFILL_PROC, req.input_length);
        const bool competing = !d_proc_ready_[cloud].empty() ||
                               active_decode_requests_[cloud] > 0 ||
                               p_proc_ready_[cloud].size() > 1;
        if (!competing) {
            return layer_count_;
        }
        const double token_multiple = layer_count_ <= 8 ? 2.0 : 0.5;
        const double target_duration = max(
            4.0 * schedule_cost_,
            min(0.25 * slo_tdr_, token_multiple * slo_tpot_)
        );
        int piece_layers = static_cast<int>(ceil(
            target_duration * layer_count_ / max(1e-12, full_duration)
        ));
        piece_layers = max(1, min(piece_layers, remaining_layers));
        return req.next_prefill_layer + piece_layers;
    }

    vector<Candidate> cloud_candidates(int cloud) {
        vector<Candidate> candidates;
        auto add = [&](TaskKind kind, deque<int>& queue, RequestState expected, int rank) {
            if (!queue_available(queue, expected)) {
                return;
            }
            const int request_id = queue.front();
            const Request& req = request(request_id);
            candidates.push_back(
                {kind, request_id, req.ready_sequence, request_urgency(kind, req), rank}
            );
        };
        add(TaskKind::P_PROC, p_proc_ready_[cloud], RequestState::READY_P_PROC, 1);
        add(TaskKind::D_PROC, d_proc_ready_[cloud], RequestState::READY_D_PROC, 0);

        if constexpr (kOptimizationLevel < 5) {
            sort(candidates.begin(), candidates.end(), [](const Candidate& left, const Candidate& right) {
                if (left.sequence != right.sequence) {
                    return left.sequence < right.sequence;
                }
                return left.stage_rank < right.stage_rank;
            });
        } else {
            sort(candidates.begin(), candidates.end(), [this](const Candidate& left, const Candidate& right) {
                const bool left_overdue = latency_weight_ > 0.8 && left.urgency >= 1.0;
                const bool right_overdue = latency_weight_ > 0.8 && right.urgency >= 1.0;
                if (left_overdue != right_overdue) {
                    return left_overdue;
                }
                if (left_overdue) {
                    const double left_priority =
                        left.urgency + (left.kind == TaskKind::D_PROC ? 0.15 : 0.0);
                    const double right_priority =
                        right.urgency + (right.kind == TaskKind::D_PROC ? 0.15 : 0.0);
                    if (abs(left_priority - right_priority) > 1e-12) {
                        return left_priority > right_priority;
                    }
                }
                if (left.sequence != right.sequence) {
                    return left.sequence < right.sequence;
                }
                return left.stage_rank < right.stage_rank;
            });
        }
        if constexpr (kOptimizationLevel >= 7) {
            bool link_constrained = bandwidth_gbps_ < 0.1;
            if (queue_available(p_proc_ready_[cloud], RequestState::READY_P_PROC)) {
                const Request& pending_prefill = request(p_proc_ready_[cloud].front());
                link_constrained = link_constrained || (active_decode_requests_[cloud] > 0 &&
                    transfer_time(
                        static_cast<long long>(pending_prefill.input_length) * bytes_per_token_
                    ) > slo_tpot_);
            }
            if (link_constrained) {
                stable_sort(
                    candidates.begin(),
                    candidates.end(),
                    [](const Candidate& left, const Candidate& right) {
                        return left.stage_rank < right.stage_rank;
                    }
                );
            }
        }
        return candidates;
    }

    optional<string> dispatch_cloud(int cloud, bool allow_wait) {
        if (cloud_busy_[cloud]) {
            return nullopt;
        }
        vector<Candidate> candidates = cloud_candidates(cloud);
        for (const Candidate& candidate : candidates) {
            if (candidate.kind == TaskKind::P_PROC) {
                const int request_id = take_front(
                    p_proc_ready_[cloud], RequestState::READY_P_PROC, 1
                ).front();
                Request& req = request(request_id);
                const int layer_start = req.next_prefill_layer;
                const int layer_end = choose_prefill_piece_end(req, cloud);
                const double piece_duration =
                    duration(DurationColumn::PREFILL_PROC, req.input_length) *
                    (layer_end - layer_start) / static_cast<double>(layer_count_);
                pending_prefill_work_[cloud] = max(
                    0.0, pending_prefill_work_[cloud] - piece_duration
                );
                req.state = RequestState::RUNNING_P_PROC;
                cloud_busy_[cloud] = true;
                cloud_busy_until_[cloud] = current_time_ + schedule_cost_ + piece_duration;
                return "C" + to_string(cloud) + " P PROC " + to_string(layer_start) + " " +
                       to_string(layer_end) + " " + to_string(cloud) + " " +
                       to_string(request_id);
            }

            if (candidate.kind == TaskKind::D_PROC) {
                const int available = static_cast<int>(d_proc_ready_[cloud].size());
                const int oldest = queue_front(
                    d_proc_ready_[cloud], RequestState::READY_D_PROC
                );
                if (should_wait_for_group(
                        TaskKind::D_PROC,
                        DurationColumn::DECODE_PROC,
                        cloud,
                        available,
                        request(oldest).ready_time,
                        allow_wait
                    )) {
                    continue;
                }
                const int group_size = best_group_size(DurationColumn::DECODE_PROC, available);
                vector<int> members = take_front(
                    d_proc_ready_[cloud], RequestState::READY_D_PROC, group_size
                );
                for (int request_id : members) {
                    request(request_id).state = RequestState::RUNNING_D_PROC;
                }
                cloud_busy_[cloud] = true;
                cloud_busy_until_[cloud] = current_time_ + schedule_cost_ +
                                           duration(DurationColumn::DECODE_PROC, group_size);
                return "C" + to_string(cloud) + " D PROC " + to_string(cloud) + " " +
                       to_string(group_size) + join_members(members);
            }
        }
        return nullopt;
    }

    bool any_ready_work() {
        if (queue_available(p_pre_ready_, RequestState::READY_P_PRE) ||
            queue_available(p_post_ready_, RequestState::READY_P_POST) ||
            queue_available(d_pre_ready_, RequestState::READY_D_PRE) ||
            queue_available(d_post_ready_, RequestState::READY_D_POST)) {
            return true;
        }
        for (int cloud = 0; cloud < cloud_count_; ++cloud) {
            if (queue_available(p_proc_ready_[cloud], RequestState::READY_P_PROC) ||
                queue_available(d_proc_ready_[cloud], RequestState::READY_D_PROC)) {
                return true;
            }
        }
        return false;
    }

    vector<string> dispatch_ready_work() {
        vector<string> assignments;
        assignments.reserve(cloud_count_ + 1);

        bool allow_wait = has_known_future_event();
        if (optional<string> edge = dispatch_edge(allow_wait)) {
            assignments.push_back(*edge);
        }

        for (int cloud = 0; cloud < cloud_count_; ++cloud) {
            allow_wait = has_known_future_event();
            if (optional<string> task = dispatch_cloud(cloud, allow_wait)) {
                assignments.push_back(*task);
            }
        }

        if (assignments.empty() && any_ready_work() && !has_known_future_event()) {
            if (optional<string> edge = dispatch_edge(false)) {
                assignments.push_back(*edge);
            }
            for (int cloud = 0; cloud < cloud_count_; ++cloud) {
                if (optional<string> task = dispatch_cloud(cloud, false)) {
                    assignments.push_back(*task);
                }
            }
        }

        if (assignments.size() > static_cast<size_t>(cloud_count_ + 1)) {
            fail("too many assignments in one response");
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

    LayeredScheduler scheduler;
    if (!scheduler.read_startup()) {
        return 0;
    }
    scheduler.run();
    return 0;
}
