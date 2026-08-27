#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

using namespace std;

#ifndef OPT_LEVEL
#define OPT_LEVEL 20
#endif

#ifndef BACKPRESSURE_OLDER_PPROC
#define BACKPRESSURE_OLDER_PPROC 1
#endif

#ifndef COHERENT_DECODE_BATCH
#define COHERENT_DECODE_BATCH 4
#endif

// SUBMISSION_FEATURE_BEGIN dynamic_coherent_dpost
#ifndef DYNAMIC_COHERENT_DPOST
#define DYNAMIC_COHERENT_DPOST 1
#endif

#ifndef DYNAMIC_COHERENT_DISPERSION_RATIO
#define DYNAMIC_COHERENT_DISPERSION_RATIO 0.15
#endif

#ifndef DYNAMIC_COHERENT_MAX_GROUP
#define DYNAMIC_COHERENT_MAX_GROUP 8
#endif
// SUBMISSION_FEATURE_END dynamic_coherent_dpost

// SUBMISSION_FEATURE_BEGIN initial_decode_barrier
#ifndef INITIAL_DECODE_BARRIER
#define INITIAL_DECODE_BARRIER 1
#endif
#ifndef INITIAL_DECODE_MIN_LATENCY_S_RATIO
#define INITIAL_DECODE_MIN_LATENCY_S_RATIO 80.0
#endif
#ifndef INITIAL_DECODE_MIN_SAVINGS_TRANSFERS
#define INITIAL_DECODE_MIN_SAVINGS_TRANSFERS 3.0
#endif
#ifndef INITIAL_DECODE_REQUIRE_MONOTONIC
#define INITIAL_DECODE_REQUIRE_MONOTONIC 1
#endif
#ifndef INITIAL_DECODE_MAX_READY_FRACTION
#define INITIAL_DECODE_MAX_READY_FRACTION 0.25
#endif
// SUBMISSION_FEATURE_END initial_decode_barrier

// SUBMISSION_FEATURE_BEGIN learned_policy
#ifndef LEARNED_POLICY
#define LEARNED_POLICY 1
#endif
// SUBMISSION_FEATURE_END learned_policy

// SUBMISSION_FEATURE_BEGIN learned_policy_training
#ifndef LEARNED_POLICY_TRACE
#define LEARNED_POLICY_TRACE 0
#endif
// SUBMISSION_FEATURE_END learned_policy_training

// SUBMISSION_FEATURE_BEGIN exact_dpost_partition
#ifndef EXACT_DPOST_PARTITION
#define EXACT_DPOST_PARTITION 0
#endif
// SUBMISSION_FEATURE_END exact_dpost_partition

// SUBMISSION_FEATURE_BEGIN censored_completion_index
#ifndef CENSORED_COMPLETION_INDEX
#define CENSORED_COMPLETION_INDEX 0
#endif
#ifndef CENSORED_COMPLETION_MIN_REACHED
#define CENSORED_COMPLETION_MIN_REACHED 8
#endif
// SUBMISSION_FEATURE_END censored_completion_index

// SUBMISSION_FEATURE_BEGIN objective_margin_rollout
#ifndef OBJECTIVE_MARGIN_ROLLOUT
#define OBJECTIVE_MARGIN_ROLLOUT 0
#endif
#ifndef OBJECTIVE_MARGIN_ROLLOUT_THRESHOLD
#define OBJECTIVE_MARGIN_ROLLOUT_THRESHOLD 0.03
#endif
#ifndef OBJECTIVE_MARGIN_MIN_LATENCY_WEIGHT
#define OBJECTIVE_MARGIN_MIN_LATENCY_WEIGHT 0.75
#endif
#ifndef OBJECTIVE_MARGIN_MIN_URGENCY
#define OBJECTIVE_MARGIN_MIN_URGENCY 1.0
#endif
// SUBMISSION_FEATURE_END objective_margin_rollout

// SUBMISSION_FEATURE_BEGIN robust_portfolio_policy
#ifndef ROBUST_PORTFOLIO_POLICY
#define ROBUST_PORTFOLIO_POLICY 0
#endif
#ifndef ROBUST_PORTFOLIO_MARGIN
#define ROBUST_PORTFOLIO_MARGIN 0.03
#endif
// SUBMISSION_FEATURE_END robust_portfolio_policy

// SUBMISSION_FEATURE_BEGIN edge_stage_restore
#ifndef EDGE_STAGE_PRIORITY_RESTORE
#define EDGE_STAGE_PRIORITY_RESTORE 0
#endif
// SUBMISSION_FEATURE_END edge_stage_restore

// SUBMISSION_FEATURE_BEGIN link_admission_fairness
#ifndef LINK_ADMISSION_FAIRNESS
#define LINK_ADMISSION_FAIRNESS 0
#endif
// SUBMISSION_FEATURE_END link_admission_fairness

// SUBMISSION_FEATURE_BEGIN prefill_cohort_wait
#ifndef PREFILL_COHORT_WAIT
#define PREFILL_COHORT_WAIT 0
#endif
// SUBMISSION_FEATURE_END prefill_cohort_wait

// SUBMISSION_FEATURE_BEGIN ppost_cohort_seed
#ifndef PPOST_COHORT_SEED
#define PPOST_COHORT_SEED 1
#endif
// SUBMISSION_FEATURE_END ppost_cohort_seed

// SUBMISSION_FEATURE_BEGIN cohort_dpost
#ifndef COHORT_DPOST_WAIT
#define COHORT_DPOST_WAIT 1
#endif

#ifndef COHORT_DPOST_MAX_WAIT_FRACTION
#define COHORT_DPOST_MAX_WAIT_FRACTION 0.001
#endif

// SUBMISSION_FEATURE_END cohort_dpost

// SUBMISSION_FEATURE_BEGIN terminal_dpost
#ifndef DPOST_CLEARANCE_RATIO
#define DPOST_CLEARANCE_RATIO 0.995
#endif

#ifndef DPOST_SCORE_MARGIN
#define DPOST_SCORE_MARGIN 0.1
#endif

#ifndef DPOST_RELAXED_MAX_LATENCY_WEIGHT
#define DPOST_RELAXED_MAX_LATENCY_WEIGHT 0.75
#endif
// SUBMISSION_FEATURE_END terminal_dpost

// SUBMISSION_FEATURE_BEGIN terminal_dproc
#ifndef DPROC_CLEARANCE_RATIO
#define DPROC_CLEARANCE_RATIO 0.97
#endif

#ifndef DPROC_SCORE_MARGIN
#define DPROC_SCORE_MARGIN 1.0
#endif
// SUBMISSION_FEATURE_END terminal_dproc

// SUBMISSION_FEATURE_BEGIN experimental_grouping
#ifndef GROUP_RATE_WEIGHT
#define GROUP_RATE_WEIGHT 2.0965663201961706
#endif

#ifndef GROUP_EFFICIENCY_WEIGHT
#define GROUP_EFFICIENCY_WEIGHT 0.4722697992083653
#endif

#ifndef GROUP_LATENCY_WEIGHT
#define GROUP_LATENCY_WEIGHT 0.5648520186162361
#endif

#ifndef GROUP_URGENCY_WEIGHT
#define GROUP_URGENCY_WEIGHT 0.18882547816763579
#endif

#ifndef GROUP_COMPLETION_WEIGHT
#define GROUP_COMPLETION_WEIGHT 0.06047792612072621
#endif

#ifndef GROUP_FANOUT_PENALTY
#define GROUP_FANOUT_PENALTY 0.07390699237638261
#endif

#ifndef GROUP_EXCLUDED_PENALTY
#define GROUP_EXCLUDED_PENALTY 0.9014739064049107
#endif

#ifndef GROUP_DISPERSION_PENALTY
#define GROUP_DISPERSION_PENALTY 0.0682778510293531
#endif

#ifndef GROUP_DECISION_MARGIN
#define GROUP_DECISION_MARGIN 0.040219567204485676
#endif

#ifndef GROUP_INTERACTION_EFFICIENCY
#define GROUP_INTERACTION_EFFICIENCY 0.0
#endif

#ifndef GROUP_INTERACTION_URGENCY
#define GROUP_INTERACTION_URGENCY 0.0
#endif

#ifndef GROUP_INTERACTION_CONGESTION
#define GROUP_INTERACTION_CONGESTION 0.0
#endif
// SUBMISSION_FEATURE_END experimental_grouping

static_assert(1 <= OPT_LEVEL && OPT_LEVEL <= 20, "OPT_LEVEL must be in [1, 20]");

namespace {

constexpr int kOptimizationLevel = OPT_LEVEL;
// SUBMISSION_FEATURE_BEGIN pre20_only
constexpr bool kBackpressureOlderPProc = BACKPRESSURE_OLDER_PPROC != 0;
// SUBMISSION_FEATURE_END pre20_only
// SUBMISSION_FEATURE_BEGIN experimental_grouping
constexpr bool kExperimentalGrouping = 16 <= OPT_LEVEL && OPT_LEVEL <= 18;
// SUBMISSION_FEATURE_END experimental_grouping
// SUBMISSION_FEATURE_BEGIN terminal_dpost
constexpr bool kTerminalDPostOptimizer = OPT_LEVEL >= 19;
// SUBMISSION_FEATURE_END terminal_dpost
// SUBMISSION_FEATURE_BEGIN terminal_dproc
constexpr bool kTerminalDProcOptimizer = OPT_LEVEL >= 20;
// SUBMISSION_FEATURE_END terminal_dproc

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
    int produced_tokens = 0;
    // SUBMISSION_FEATURE_BEGIN prefill_cohort_wait
    int running_prefill_layer_end = 0;
    // SUBMISSION_FEATURE_END prefill_cohort_wait
};

struct Candidate {
    TaskKind kind;
    int request_id;
    uint64_t sequence;
    double urgency;
    int stage_rank;
    double action_value = 0;
};

struct TransferPrediction {
    double finish_time = 0;
    long long size_bytes = 0;
    int remote = -1;
    bool decode = false;
};

// SUBMISSION_FEATURE_BEGIN experimental_grouping
struct GroupEvaluation {
    double token_finish = 0;
    double horizon = 0;
    double normalized_rate = 0;
    double service_efficiency = 0;
    double waiting_quality = 0;
    double urgency_progress = 0;
    double completion_potential = 0;
    double fanout_pressure = 0;
    double excluded_pressure = 0;
    double finish_dispersion = 0;
    double link_pressure = 0;
    int fanout = 0;
};
// SUBMISSION_FEATURE_END experimental_grouping

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
        // SUBMISSION_FEATURE_BEGIN experimental_grouping
        if constexpr (kExperimentalGrouping) {
            build_group_size_cache();
        }
        // SUBMISSION_FEATURE_END experimental_grouping

        cloud_busy_.assign(cloud_count_, false);
        cloud_busy_until_.assign(cloud_count_, 0);
        cloud_running_kind_.resize(cloud_count_);
        // SUBMISSION_FEATURE_BEGIN terminal_dproc
        cloud_running_group_size_.assign(cloud_count_, 0);
        // SUBMISSION_FEATURE_END terminal_dproc
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
    // SUBMISSION_FEATURE_BEGIN pre20_only
    int next_round_robin_cloud_ = 0;
    // SUBMISSION_FEATURE_END pre20_only

    array<vector<pair<int, double>>, 6> duration_curves_;
    // SUBMISSION_FEATURE_BEGIN experimental_grouping
    array<vector<int>, 6> best_group_size_cache_;
    // SUBMISSION_FEATURE_END experimental_grouping
    vector<Request> requests_;

    bool edge_busy_ = false;
    optional<TaskKind> edge_running_kind_;
    vector<bool> cloud_busy_;
    vector<double> cloud_busy_until_;
    vector<optional<TaskKind>> cloud_running_kind_;
    // SUBMISSION_FEATURE_BEGIN terminal_dproc
    vector<int> cloud_running_group_size_;
    // SUBMISSION_FEATURE_END terminal_dproc
    vector<int> active_requests_;
    vector<int> active_decode_requests_;
    int total_active_decode_requests_ = 0;
    vector<double> pending_prefill_work_;
    vector<int> coherent_decode_batch_;

    // SUBMISSION_FEATURE_BEGIN learned_policy
    mutable int learned_policy_action_ = -2;
    // SUBMISSION_FEATURE_END learned_policy

    // SUBMISSION_FEATURE_BEGIN learned_policy_training
    mutable bool learned_policy_trace_emitted_ = false;
    // SUBMISSION_FEATURE_END learned_policy_training

    // SUBMISSION_FEATURE_BEGIN learned_policy
    // SUBMISSION_FEATURE_BEGIN robust_portfolio_policy
    int robust_portfolio_action(const array<double, 18>& features) const {
        static constexpr double mean[18] = {0.50774148,0.898836418,0.397077548,0.646194889,0.0925125194,0.235348771,0.0402909415,0.16422249,0.784510723,0.727351207,0.777676842,0.155096643,0,0,0.307276382,0.0757275024,0.302985003,0.726976836};
        static constexpr double scale[18] = {0.175967918,0.218541094,0.167058161,0.291016369,0.0845465836,0.179322139,0.0564337223,0.199913242,0.298836849,0.326921622,0.293998939,0.298498574,1,1,0.24776391,0.0908237641,0.371203038,0.206631262};
        static constexpr signed char weight1[144] = {20,-39,47,-76,49,66,27,85,-20,11,40,78,8,26,-39,5,-57,20,-100,29,2,71,-8,-28,-51,52,107,-2,-11,31,34,-21,1,12,-12,-21,5,-40,-95,25,17,17,-102,42,36,-52,-2,31,14,-33,9,9,-9,17,-71,31,28,-10,20,-35,7,-93,-127,-46,1,-2,2,-78,-7,-33,-40,-4,59,36,18,-47,-21,60,62,37,36,-58,65,26,22,-64,-10,27,88,-26,52,43,65,6,-91,-44,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-32,-33,3,-53,-67,62,39,-5,52,19,-21,30,23,-51,-75,1,2,-102,-37,45,41,-39,13,30,28,-92,6,-25,-17,65,-48,61};
        static constexpr double bias1[8] = {-0.466494501,0.0270871619,-0.405157813,-0.234463854,-0.103925918,-0.249800501,-0.432920974,0.34533604};
        static constexpr signed char weight2[48] = {35,17,-94,66,108,99,63,96,102,92,88,81,-84,-86,-109,-106,-118,-119,11,84,118,94,96,95,33,53,9,72,78,90,96,110,106,106,106,102,121,109,104,115,126,127,64,73,105,70,59,52};
        static constexpr double bias2[6] = {-0.215685277,-0.255089354,-0.289218616,-0.245952851,-0.232221685,-0.206909355};
        array<double, 8> hidden{};
        for (int j = 0; j < 8; ++j) {
            double value = bias1[j];
            for (int i = 0; i < 18; ++i) {
                value += 0.004216532154130618 * weight1[i * 8 + j] *
                         (features[i] - mean[i]) / scale[i];
            }
            hidden[j] = max(0.0, value);
        }
        int best_action = -1;
        double best_value = ROBUST_PORTFOLIO_MARGIN;
        for (int action = 0; action < 6; ++action) {
            double value = bias2[action];
            for (int j = 0; j < 8; ++j) {
                value += 0.003504114792716609 * weight2[j * 6 + action] * hidden[j];
            }
            if (value > best_value) {
                best_value = value;
                best_action = action;
            }
        }
        return best_action;
    }
    // SUBMISSION_FEATURE_END robust_portfolio_policy

    int learned_policy_action(const array<double, 18>& features) const {
        // SUBMISSION_FEATURE_BEGIN robust_portfolio_policy
        if constexpr (ROBUST_PORTFOLIO_POLICY) {
            const int robust_action = robust_portfolio_action(features);
            if (robust_action >= 0) {
                return robust_action;
            }
        }
        // SUBMISSION_FEATURE_END robust_portfolio_policy
        static constexpr double mean[18] = {0.51116079,0.91275028,0.36819503,0.73329929,0.096293376,0.2704419,0.042277165,0.14893834,0.78495524,0.72835505,0.78319485,0.16979815,0,0,0.23552308,0.062818557,0.43000335,0.7479205};
        static constexpr double scale[18] = {0.17476555,0.19849252,0.17155202,0.27118136,0.090414801,0.20926342,0.060217092,0.18751229,0.29148215,0.32325564,0.29298162,0.30844069,1,1,0.25209581,0.085901774,0.42382806,0.21217678};
        static constexpr signed char weight1[144] = {127,41,82,20,99,61,26,19,81,37,109,-29,-31,-21,4,-29,67,84,41,30,38,-36,3,-22,-14,12,14,20,3,60,-3,43,-39,-32,-14,-51,-29,-14,20,2,-9,93,48,-42,-30,14,-13,-24,-17,0,7,-10,13,-12,-99,-51,-91,-21,-76,-44,-36,-38,-50,-37,-26,5,-44,-82,-78,29,-52,-39,14,27,-35,-90,-104,11,-36,4,-56,-53,38,-26,-82,55,115,94,42,-42,1,-60,-56,-66,31,-18,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,-92,34,39,27,65,27,45,-55,-21,-58,-39,-40,-27,-19,-40,-24,-61,32,3,6,21,55,37,55,-60,12,-99,-86,38,7,20};
        static constexpr double bias1[8] = {-1.6266147,-1.0087565,-0.61284763,-0.17716989,-0.67024784,-0.26747773,-0.35872538,0.038399282};
        static constexpr signed char weight2[56] = {95,95,125,122,85,84,83,84,83,127,123,70,69,67,-76,-70,-123,-121,-72,-71,-71,76,94,95,92,92,91,96,-87,-108,-102,-103,-105,-104,-109,63,64,62,56,84,85,89,63,41,92,88,94,96,100,-48,-38,-46,-44,-90,-93,-99};
        static constexpr double bias2[7] = {-0.078010351,-0.064512272,-0.12885885,-0.058472153,-0.014434206,-0.0079187007,-0.0069188679};
        array<double, 8> hidden{};
        for (int j = 0; j < 8; ++j) {
            double value = bias1[j];
            for (int i = 0; i < 18; ++i) {
                value += 0.0082981787 * weight1[i * 8 + j] *
                         (features[i] - mean[i]) / scale[i];
            }
            hidden[j] = max(0.0, value);
        }
        int best_action = -1;
        double best_value = 0.6;
        for (int action = 0; action < 6; ++action) {
            double value = bias2[action];
            for (int j = 0; j < 8; ++j) {
                value += 0.0069224944 * weight2[j * 7 + action] * hidden[j];
            }
            if (value > best_value) {
                best_value = value;
                best_action = action;
            }
        }
        return best_action;
    }
    // SUBMISSION_FEATURE_END learned_policy

    int pending_up_transfers_ = 0;
    int pending_down_transfers_ = 0;
    long long pending_up_bytes_ = 0;
    long long pending_down_bytes_ = 0;
    double predicted_up_tail_ = 0;
    double predicted_down_tail_ = 0;
    deque<TransferPrediction> predicted_up_queue_;
    deque<TransferPrediction> predicted_down_queue_;

    vector<int> completed_output_lengths_;
    array<vector<int>, 13> completed_output_lengths_by_input_bin_;
    // SUBMISSION_FEATURE_BEGIN censored_completion_index
    static constexpr int kCompletionAgeBuckets = 257;
    array<array<int, kCompletionAgeBuckets>, 13> completion_reached_by_input_{};
    array<array<int, kCompletionAgeBuckets>, 13> completion_finished_by_input_{};
    array<int, kCompletionAgeBuckets> completion_reached_{};
    array<int, kCompletionAgeBuckets> completion_finished_{};
    // SUBMISSION_FEATURE_END censored_completion_index
    // SUBMISSION_FEATURE_BEGIN terminal_dpost
    double observed_tdr_sum_ = 0;
    int observed_tdr_count_ = 0;
    double observed_tpot_sum_ = 0;
    long long observed_tpot_count_ = 0;
    // SUBMISSION_FEATURE_END terminal_dpost

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

    // SUBMISSION_FEATURE_BEGIN experimental_grouping
    void build_group_size_cache() {
        constexpr int kMaximumRequests = 2000;
        for (int raw_column = static_cast<int>(DurationColumn::DECODE_PRE);
             raw_column <= static_cast<int>(DurationColumn::DECODE_POST);
             ++raw_column) {
            const DurationColumn column = static_cast<DurationColumn>(raw_column);
            vector<int>& cache = best_group_size_cache_[raw_column];
            cache.assign(kMaximumRequests + 1, 1);
            int best_size = 1;
            double best_rate = -numeric_limits<double>::infinity();
            for (int size = 1; size <= kMaximumRequests; ++size) {
                double service = schedule_cost_ + duration(column, size);
                if (column == DurationColumn::DECODE_PRE ||
                    column == DurationColumn::DECODE_PROC) {
                    service += transfer_time(
                        static_cast<long long>(size) * bytes_per_token_
                    );
                }
                if (column == DurationColumn::DECODE_PRE &&
                    downstream_group_is_hostile(size)) {
                    service += schedule_cost_ +
                               duration(DurationColumn::DECODE_PROC, size) +
                               transfer_time(
                                   static_cast<long long>(size) * bytes_per_token_
                               ) +
                               schedule_cost_ +
                               duration(DurationColumn::DECODE_POST, size);
                } else if (column == DurationColumn::DECODE_PROC &&
                           downstream_group_is_hostile(size)) {
                    service += schedule_cost_ +
                               duration(DurationColumn::DECODE_POST, size);
                }
                const double rate = size / max(1e-12, service);
                if (rate > best_rate + 1e-12) {
                    best_rate = rate;
                    best_size = size;
                }
                cache[size] = best_size;
            }
        }
    }
    // SUBMISSION_FEATURE_END experimental_grouping

    double transfer_time(long long size_bytes, int transfer_count = 1) const {
        return transfer_count * latency_ms_ +
               8.0 * static_cast<double>(size_bytes) / (bandwidth_gbps_ * 1'000'000.0);
    }

    int input_length_bin(int input_length) const {
        int bin = 0;
        while (bin + 1 < static_cast<int>(completed_output_lengths_by_input_bin_.size()) &&
               (1 << bin) < input_length) {
            ++bin;
        }
        return bin;
    }

    void enqueue_transfer(
        const string& direction,
        long long size_bytes,
        int remote,
        bool decode
    ) {
        deque<TransferPrediction>* queue = nullptr;
        double* tail = nullptr;
        int* pending_count = nullptr;
        long long* pending_bytes = nullptr;
        if (direction == "UP") {
            queue = &predicted_up_queue_;
            tail = &predicted_up_tail_;
            pending_count = &pending_up_transfers_;
            pending_bytes = &pending_up_bytes_;
        } else if (direction == "DOWN") {
            queue = &predicted_down_queue_;
            tail = &predicted_down_tail_;
            pending_count = &pending_down_transfers_;
            pending_bytes = &pending_down_bytes_;
        } else {
            fail("invalid transfer direction");
        }

        const double start = max(current_time_, *tail);
        const double finish = start + transfer_time(size_bytes);
        queue->push_back({finish, size_bytes, remote, decode});
        *tail = finish;
        ++*pending_count;
        *pending_bytes += size_bytes;
    }

    void complete_transfer(const string& direction, long long size_bytes, int remote) {
        deque<TransferPrediction>* queue = nullptr;
        double* tail = nullptr;
        int* pending_count = nullptr;
        long long* pending_bytes = nullptr;
        if (direction == "UP") {
            queue = &predicted_up_queue_;
            tail = &predicted_up_tail_;
            pending_count = &pending_up_transfers_;
            pending_bytes = &pending_up_bytes_;
        } else if (direction == "DOWN") {
            queue = &predicted_down_queue_;
            tail = &predicted_down_tail_;
            pending_count = &pending_down_transfers_;
            pending_bytes = &pending_down_bytes_;
        } else {
            fail("invalid completed transfer direction");
        }
        if (*pending_count <= 0 || *pending_bytes < size_bytes || queue->empty()) {
            fail(direction + " transfer accounting underflow");
        }
        const TransferPrediction predicted = queue->front();
        if (predicted.size_bytes != size_bytes || predicted.remote != remote) {
            fail(direction + " transfer completion violated predicted FIFO order");
        }
        queue->pop_front();
        --*pending_count;
        *pending_bytes -= size_bytes;
        if (queue->empty()) {
            *tail = current_time_;
        }
    }

    double predicted_link_tail(const string& direction) const {
        return direction == "UP" ? predicted_up_tail_ : predicted_down_tail_;
    }

    double predicted_link_delay(const string& direction) const {
        return max(0.0, predicted_link_tail(direction) - current_time_);
    }

    double next_known_event_time() const {
        double result = numeric_limits<double>::infinity();
        if (edge_busy_) {
            result = min(result, edge_busy_until_);
        }
        for (int cloud = 0; cloud < cloud_count_; ++cloud) {
            if (cloud_busy_[cloud]) {
                result = min(result, cloud_busy_until_[cloud]);
            }
        }
        if (!predicted_up_queue_.empty()) {
            result = min(result, predicted_up_queue_.front().finish_time);
        }
        if (!predicted_down_queue_.empty()) {
            result = min(result, predicted_down_queue_.front().finish_time);
        }
        return result;
    }

    bool has_known_future_event() const {
        return isfinite(next_known_event_time());
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
        req.produced_tokens = 0;
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
            edge_running_kind_.reset();
            return;
        }
        const int cloud = cloud_from_server(server);
        if (!cloud_busy_[cloud]) {
            fail("TDN attempted to free an idle cloud");
        }
        cloud_busy_[cloud] = false;
        cloud_busy_until_[cloud] = current_time_;
        cloud_running_kind_[cloud].reset();
        // SUBMISSION_FEATURE_BEGIN terminal_dproc
        cloud_running_group_size_[cloud] = 0;
        // SUBMISSION_FEATURE_END terminal_dproc
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
            enqueue_transfer(
                "UP",
                static_cast<long long>(req.input_length) * bytes_per_token_,
                req.cloud,
                false
            );
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
            // SUBMISSION_FEATURE_BEGIN prefill_cohort_wait
            if constexpr (PREFILL_COHORT_WAIT) {
                if (req.running_prefill_layer_end != layer_end) {
                    fail("P PROC TDN did not match the tracked piece end");
                }
                req.running_prefill_layer_end = 0;
            }
            // SUBMISSION_FEATURE_END prefill_cohort_wait
            req.next_prefill_layer = layer_end;
            if (layer_end == layer_count_) {
                req.state = RequestState::WAITING_PREFILL_DOWN;
                enqueue_transfer(
                    "DOWN",
                    static_cast<long long>(req.input_length) * bytes_per_token_,
                    req.cloud,
                    false
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
            // SUBMISSION_FEATURE_BEGIN terminal_dpost
            observed_tdr_sum_ += current_time_ - req.arrival_time;
            ++observed_tdr_count_;
            // SUBMISSION_FEATURE_END terminal_dpost
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
            vector<int> members_per_cloud(cloud_count_, 0);
            for (int request_id : members) {
                Request& req = request(request_id);
                expect_state(req, RequestState::RUNNING_D_PRE, "D PRE TDN");
                req.state = RequestState::WAITING_DECODE_UP;
                ++members_per_cloud[req.cloud];
            }
            for (int cloud = 0; cloud < cloud_count_; ++cloud) {
                if (members_per_cloud[cloud] == 0) {
                    continue;
                }
                enqueue_transfer(
                    "UP",
                    static_cast<long long>(members_per_cloud[cloud]) * bytes_per_token_,
                    cloud,
                    true
                );
            }
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
            enqueue_transfer(
                "DOWN",
                static_cast<long long>(members.size()) * bytes_per_token_,
                cloud,
                true
            );
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
                // SUBMISSION_FEATURE_BEGIN terminal_dpost
                if (req.produced_tokens > 0) {
                    observed_tpot_sum_ += current_time_ - req.decode_clock_start;
                    ++observed_tpot_count_;
                }
                // SUBMISSION_FEATURE_END terminal_dpost
                ++req.produced_tokens;
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
        complete_transfer(direction, size_bytes, cloud);

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
        completed_output_lengths_.push_back(req.produced_tokens);
        completed_output_lengths_by_input_bin_[input_length_bin(req.input_length)].push_back(
            req.produced_tokens
        );
    }

    void finalize_decode_completions() {
        for (int request_id : d_post_completed_this_frame_) {
            Request& req = request(request_id);
            // SUBMISSION_FEATURE_BEGIN censored_completion_index
            if constexpr (CENSORED_COMPLETION_INDEX) {
                const int age = min(kCompletionAgeBuckets - 1, req.produced_tokens);
                const int input_bin = input_length_bin(req.input_length);
                ++completion_reached_[age];
                ++completion_reached_by_input_[input_bin][age];
                if (req.state == RequestState::FINISHED) {
                    ++completion_finished_[age];
                    ++completion_finished_by_input_[input_bin][age];
                }
            }
            // SUBMISSION_FEATURE_END censored_completion_index
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

    vector<int> collect_ready(deque<int>& queue, RequestState expected) {
        queue.erase(
            remove_if(
                queue.begin(),
                queue.end(),
                [&](int request_id) { return request(request_id).state != expected; }
            ),
            queue.end()
        );
        return vector<int>(queue.begin(), queue.end());
    }

    vector<int> take_selected(
        deque<int>& queue,
        RequestState expected,
        const vector<int>& selected
    ) {
        vector<int> result;
        result.reserve(selected.size());
        for (int request_id : selected) {
            expect_state(request(request_id), expected, "selected ready task");
            const auto position = find(queue.begin(), queue.end(), request_id);
            if (position == queue.end()) {
                fail("selected request was not present in its ready queue");
            }
            queue.erase(position);
            result.push_back(request_id);
        }
        return result;
    }

    set<int> candidate_group_sizes(int available) const {
        set<int> candidates = {1, available};
        for (int column = static_cast<int>(DurationColumn::DECODE_PRE);
             column <= static_cast<int>(DurationColumn::DECODE_POST);
             ++column) {
            for (const auto& [size, ignored] : duration_curves_[column]) {
                (void)ignored;
                for (int candidate : {size - 1, size, size + 1}) {
                    if (1 <= candidate && candidate <= available) {
                        candidates.insert(candidate);
                    }
                }
            }
        }
        return candidates;
    }

    bool downstream_group_is_hostile(int size) const {
        if (size <= 1) {
            return false;
        }
        double best_per_member = numeric_limits<double>::infinity();
        for (int candidate = 1; candidate <= size; ++candidate) {
            best_per_member = min(
                best_per_member,
                (schedule_cost_ + duration(DurationColumn::DECODE_POST, candidate)) /
                    candidate
            );
        }
        const double current_per_member =
            (schedule_cost_ + duration(DurationColumn::DECODE_POST, size)) / size;
        return current_per_member > 1.5 * best_per_member + 1e-12;
    }

    double next_compatible_event_time(TaskKind kind, int cloud) const {
        double result = numeric_limits<double>::infinity();
        if (kind == TaskKind::D_PRE && edge_busy_ &&
            edge_running_kind_ == TaskKind::D_POST) {
            result = min(result, edge_busy_until_);
        }
        if (kind == TaskKind::D_PROC) {
            for (const TransferPrediction& transfer : predicted_up_queue_) {
                if (transfer.decode && transfer.remote == cloud) {
                    result = min(result, transfer.finish_time);
                    break;
                }
            }
        }
        return result;
    }

    double expected_remaining_tokens(const Request& req) const {
        auto survivor_mean = [&](const vector<int>& samples, int minimum_samples)
            -> optional<double> {
            double sum = 0;
            int count = 0;
            for (int length : samples) {
                if (length > req.produced_tokens) {
                    sum += length - req.produced_tokens;
                    ++count;
                }
            }
            if (count < minimum_samples) {
                return nullopt;
            }
            return sum / count;
        };

        const vector<int>& local_samples =
            completed_output_lengths_by_input_bin_[input_length_bin(req.input_length)];
        if (optional<double> estimate = survivor_mean(local_samples, 3)) {
            return *estimate;
        }
        if (optional<double> estimate = survivor_mean(completed_output_lengths_, 5)) {
            return *estimate;
        }
        // Least-attained-service fallback when there is not enough completed history to learn
        // a survival curve. It deliberately gives new streams a short-job opportunity.
        return 1.0 + req.produced_tokens;
    }

    // SUBMISSION_FEATURE_BEGIN censored_completion_index
    double empirical_completion_index(const Request& req) const {
        const int input_bin = input_length_bin(req.input_length);
        const int next_age = min(kCompletionAgeBuckets - 1, req.produced_tokens + 1);
        if (completion_reached_[next_age] < CENSORED_COMPLETION_MIN_REACHED) {
            return 1.0 / max(1.0, expected_remaining_tokens(req));
        }
        double survival = 1.0;
        double finish_probability = 0.0;
        double expected_service = 0.0;
        double best_index = 0.0;
        for (int quantum = 1; quantum <= 16; ++quantum) {
            const int age = min(
                kCompletionAgeBuckets - 1, req.produced_tokens + quantum
            );
            int reached = completion_reached_by_input_[input_bin][age];
            int finished = completion_finished_by_input_[input_bin][age];
            if (reached < max(6, CENSORED_COMPLETION_MIN_REACHED / 2)) {
                reached = completion_reached_[age];
                finished = completion_finished_[age];
            }
            const double hazard = (finished + 1.0) / (reached + 9.0);
            expected_service += survival;
            finish_probability += survival * hazard;
            survival *= 1.0 - hazard;
            best_index = max(
                best_index,
                finish_probability / max(1e-12, expected_service)
            );
        }
        return best_index;
    }
    // SUBMISSION_FEATURE_END censored_completion_index

    double estimated_prefill_path(TaskKind kind, const Request& req) const {
        const long long bytes = static_cast<long long>(req.input_length) * bytes_per_token_;
        const double up = predicted_link_delay("UP") + transfer_time(bytes);
        const double down = predicted_link_delay("DOWN") + transfer_time(bytes);
        const double full_proc = duration(DurationColumn::PREFILL_PROC, req.input_length);
        const double remaining_fraction = layer_count_ > 0
            ? static_cast<double>(layer_count_ - req.next_prefill_layer) / layer_count_
            : 0.0;
        if (kind == TaskKind::P_PRE) {
            double best_cloud_delay = numeric_limits<double>::infinity();
            for (int cloud = 0; cloud < cloud_count_; ++cloud) {
                best_cloud_delay = min(
                    best_cloud_delay,
                    max(0.0, cloud_busy_until_[cloud] - current_time_) +
                        pending_prefill_work_[cloud]
                );
            }
            return schedule_cost_ + duration(DurationColumn::PREFILL_PRE, req.input_length) +
                   up + best_cloud_delay + schedule_cost_ + full_proc + down +
                   schedule_cost_ + duration(DurationColumn::PREFILL_POST, req.input_length);
        }
        if (kind == TaskKind::P_PROC) {
            return schedule_cost_ + remaining_fraction * full_proc + down + schedule_cost_ +
                   duration(DurationColumn::PREFILL_POST, req.input_length);
        }
        return schedule_cost_ + duration(DurationColumn::PREFILL_POST, req.input_length);
    }

    double estimated_decode_path(TaskKind kind, int group_size) const {
        const long long bytes = static_cast<long long>(group_size) * bytes_per_token_;
        const double up = predicted_link_delay("UP") + transfer_time(bytes);
        const double down = predicted_link_delay("DOWN") + transfer_time(bytes);
        const double d_pre = schedule_cost_ + duration(DurationColumn::DECODE_PRE, group_size);
        const double d_proc = schedule_cost_ + duration(DurationColumn::DECODE_PROC, group_size);
        const double d_post = schedule_cost_ + duration(DurationColumn::DECODE_POST, group_size);
        if (kind == TaskKind::D_PRE) {
            return d_pre + up + d_proc + down + d_post;
        }
        if (kind == TaskKind::D_PROC) {
            return d_proc + down + d_post;
        }
        return d_post;
    }

    double action_service_time(TaskKind kind, int group_size, const Request& req) const {
        switch (kind) {
            case TaskKind::P_PRE:
                return schedule_cost_ + duration(DurationColumn::PREFILL_PRE, req.input_length);
            case TaskKind::P_POST:
                return schedule_cost_ + duration(DurationColumn::PREFILL_POST, req.input_length);
            case TaskKind::D_PRE:
                return schedule_cost_ + duration(DurationColumn::DECODE_PRE, group_size);
            case TaskKind::D_POST:
                return schedule_cost_ + duration(DurationColumn::DECODE_POST, group_size);
            case TaskKind::P_PROC:
                return schedule_cost_ + duration(DurationColumn::PREFILL_PROC, req.input_length);
            case TaskKind::D_PROC:
                return schedule_cost_ + duration(DurationColumn::DECODE_PROC, group_size);
        }
        return 1;
    }

    double downstream_pressure(TaskKind kind, int group_size, const Request& req) const {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 14) {
            return 0;
        }
        // SUBMISSION_FEATURE_END pre20_only
        const double tdr_scale = max(1e-9, slo_tdr_);
        const double tpot_scale = max(1e-9, slo_tpot_);
        if (kind == TaskKind::P_PRE) {
            return predicted_link_delay("UP") / tdr_scale;
        }
        if (kind == TaskKind::P_PROC) {
            const long long bytes = static_cast<long long>(req.input_length) * bytes_per_token_;
            return (predicted_link_delay("DOWN") + transfer_time(bytes)) / tdr_scale;
        }
        if (kind == TaskKind::D_PRE) {
            return predicted_link_delay("UP") / tpot_scale;
        }
        if (kind == TaskKind::D_PROC) {
            const long long bytes = static_cast<long long>(group_size) * bytes_per_token_;
            return (predicted_link_delay("DOWN") + transfer_time(bytes)) / tpot_scale;
        }
        return 0;
    }

    double action_value(TaskKind kind, const Request& req, int group_size) const {
        const double service = max(1e-9, action_service_time(kind, group_size, req));
        const double urgency = request_urgency(kind, req);
        double progress = 0.4;
        if (kind == TaskKind::P_POST || kind == TaskKind::D_POST) {
            progress = 1.5;
        } else if (kind == TaskKind::P_PROC || kind == TaskKind::D_PROC) {
            progress = 1.0;
        } else if (kind == TaskKind::D_PRE) {
            progress = 0.75;
        }
        const double milestone =
            kind == TaskKind::P_PRE || kind == TaskKind::P_POST || kind == TaskKind::P_PROC
                ? estimated_prefill_path(kind, req)
                : estimated_decode_path(kind, group_size);
        const double latency_value =
            min(2.0, max(0.0, urgency - 0.5)) * progress / max(1e-9, milestone);
        const double throughput_value = static_cast<double>(group_size) / service;
        const double pressure = downstream_pressure(kind, group_size, req);
        double value = latency_weight_ * latency_value +
                       throughput_weight_ * throughput_value - 0.2 * pressure;
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 15) {
        // SUBMISSION_FEATURE_END pre20_only
            value += 0.25 * (latency_weight_ + 0.25 * throughput_weight_) /
                     max(1e-9, milestone);
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        return value;
    }

    double decode_member_value(const Request& req, TaskKind kind) const {
        const double urgency = request_urgency(kind, req);
        const double waited = max(0.0, current_time_ - req.ready_time);
        const double aging = min(2.0, waited / max(1e-9, 2.0 * slo_tpot_));
        const double learned_shortness = 1.0 / max(1.0, expected_remaining_tokens(req));
        int level = 0;
        for (int tokens = req.produced_tokens + 1; tokens > 1; tokens >>= 1) {
            ++level;
        }
        // SUBMISSION_FEATURE_BEGIN censored_completion_index
        if constexpr (CENSORED_COMPLETION_INDEX) {
            return 4.0 * max(0.0, urgency - 1.0) + urgency + aging +
                   empirical_completion_index(req) - 0.2 * level;
        }
        // SUBMISSION_FEATURE_END censored_completion_index
        return 4.0 * max(0.0, urgency - 1.0) + urgency + aging + learned_shortness -
               0.2 * level;
    }

    vector<int> take_decode_members(
        deque<int>& queue,
        RequestState expected,
        int count,
        TaskKind kind
    ) {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 13) {
            return take_front(queue, expected, count);
        }
        // SUBMISSION_FEATURE_END pre20_only
        vector<int> candidates = collect_ready(queue, expected);
        stable_sort(candidates.begin(), candidates.end(), [&](int left, int right) {
            const double left_value = decode_member_value(request(left), kind);
            const double right_value = decode_member_value(request(right), kind);
            if (abs(left_value - right_value) > 1e-12) {
                return left_value > right_value;
            }
            return request(left).ready_sequence < request(right).ready_sequence;
        });
        candidates.resize(min<int>(count, candidates.size()));
        return take_selected(queue, expected, candidates);
    }

    int take_link_aware_prefill_request() {
        clean_front(p_pre_ready_, RequestState::READY_P_PRE);
        if (p_pre_ready_.empty()) {
            fail("link-aware admission read an empty queue");
        }
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 7) {
            const int request_id = p_pre_ready_.front();
            p_pre_ready_.pop_front();
            return request_id;
        }
        // SUBMISSION_FEATURE_END pre20_only
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

    double batch_aware_cloud_score(const Request& req, int cloud) const {
        (void)req;
        const int prospective_cohort = max(1, active_requests_[cloud] + 1);
        const int candidate_size = min(
            prospective_cohort,
            best_group_size(DurationColumn::DECODE_PROC, prospective_cohort)
        );
        const double singleton = schedule_cost_ + duration(DurationColumn::DECODE_PROC, 1);
        const double grouped_per_request =
            (schedule_cost_ + duration(DurationColumn::DECODE_PROC, candidate_size)) /
            candidate_size;
        const double savings_per_iteration = max(0.0, singleton - grouped_per_request);
        const double efficiency_ratio = singleton / max(1e-9, grouped_per_request);
        const double cohort_strength = min(
            4,
            active_decode_requests_[cloud] + static_cast<int>(d_proc_ready_[cloud].size())
        );
        const int minimum_active = *min_element(active_requests_.begin(), active_requests_.end());
        const bool seed_decode_cohort = minimum_active == 0 &&
                                        active_requests_[cloud] == 1 &&
                                        active_decode_requests_[cloud] > 0;
        const double credit_scale = seed_decode_cohort ? 1.0 : 0.2;
        const double credit_cap = seed_decode_cohort ? 2.0 * singleton : 0.5 * singleton;
        const double batch_credit =
            efficiency_ratio >= 3.0 &&
                    active_requests_[cloud] <= minimum_active + 1
            ? min(
                  credit_cap,
                  credit_scale * throughput_weight_ * (1.0 + 0.5 * cohort_strength) *
                      savings_per_iteration
              )
            : 0.0;
        return cloud_load_score(cloud) - batch_credit;
    }

    int choose_cloud(const Request& req) {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel == 1) {
            const int cloud = next_round_robin_cloud_;
            next_round_robin_cloud_ = (next_round_robin_cloud_ + 1) % cloud_count_;
            return cloud;
        }
        // SUBMISSION_FEATURE_END pre20_only

        int best_cloud = 0;
        double best_load = kOptimizationLevel >= 10
            ? batch_aware_cloud_score(req, 0)
            : cloud_load_score(0);
        for (int cloud = 1; cloud < cloud_count_; ++cloud) {
            const double load = kOptimizationLevel >= 10
                ? batch_aware_cloud_score(req, cloud)
                : cloud_load_score(cloud);
            if (load + 1e-12 < best_load) {
                best_load = load;
                best_cloud = cloud;
            }
        }
        return best_cloud;
    }

    double observed_request_urgency(TaskKind kind, const Request& req) const {
        if (kind == TaskKind::P_PRE || kind == TaskKind::P_POST || kind == TaskKind::P_PROC) {
            return (current_time_ - req.arrival_time) / max(1e-9, slo_tdr_);
        }
        return (current_time_ - req.decode_clock_start) / max(1e-9, slo_tpot_);
    }

    double request_urgency(TaskKind kind, const Request& req) const {
        const double observed = observed_request_urgency(kind, req);
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 11) {
        // SUBMISSION_FEATURE_END pre20_only
            const double predicted =
                kind == TaskKind::P_PRE || kind == TaskKind::P_POST ||
                        kind == TaskKind::P_PROC
                    ? estimated_prefill_path(kind, req) / max(1e-9, slo_tdr_)
                    : estimated_decode_path(kind, 1) / max(1e-9, slo_tpot_);
            return observed + predicted;
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        return observed;
        // SUBMISSION_FEATURE_END pre20_only
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

    bool coherent_decode_enabled() const {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (!COHERENT_DECODE_BATCH || kOptimizationLevel < 20) {
            return false;
        }
        if constexpr (COHERENT_DECODE_BATCH == 1) {
            return true;
        }
        // SUBMISSION_FEATURE_END pre20_only
        const double singleton_compute =
            duration(DurationColumn::DECODE_PRE, 1) +
            duration(DurationColumn::DECODE_PROC, 1) +
            duration(DurationColumn::DECODE_POST, 1);
        return cloud_count_ >= 2 && throughput_weight_ <= 0.25 &&
               schedule_cost_ >= singleton_compute &&
               transfer_time(bytes_per_token_) <=
                   0.1 * (COHERENT_DECODE_BATCH - 1) * schedule_cost_;
    }

    // SUBMISSION_FEATURE_BEGIN dynamic_coherent_dpost
    // SUBMISSION_FEATURE_BEGIN learned_policy
    array<double, 18> learned_policy_features(
        int total,
        const vector<int>& per_cloud,
        int fanout,
        double merged_post,
        double savings,
        double ready_dispersion
    ) const {
        const auto clamp = [](double value, double upper) {
            return max(0.0, min(upper, value));
        };
        int largest_cohort = 0;
        int smallest_cohort = total;
        for (int count : per_cloud) {
            if (count > 0) {
                largest_cohort = max(largest_cohort, count);
                smallest_cohort = min(smallest_cohort, count);
            }
        }
        double produced_mean = 0.0;
        double oldest_age = 0.0;
        for (const Request& req : requests_) {
            if (req.state != RequestState::UNSEEN && req.state != RequestState::FINISHED) {
                produced_mean += req.produced_tokens;
                oldest_age = max(oldest_age, current_time_ - req.ready_time);
            }
        }
        produced_mean /= max(1, total);
        double produced_variance = 0.0;
        for (const Request& req : requests_) {
            if (req.state != RequestState::UNSEEN && req.state != RequestState::FINISHED) {
                const double delta = req.produced_tokens - produced_mean;
                produced_variance += delta * delta;
            }
        }
        produced_variance /= max(1, total);
        const auto efficiency = [&](DurationColumn column) {
            const double singleton = schedule_cost_ + duration(column, 1);
            const double grouped = schedule_cost_ + duration(column, total);
            return clamp(total * singleton / max(1e-12, grouped), 8.0) / 8.0;
        };
        const double token_transfer = transfer_time(bytes_per_token_);
        return {
            clamp(log1p(total) / log(257.0), 1.5),
            static_cast<double>(fanout) / max(1, cloud_count_),
            static_cast<double>(largest_cohort) / max(1, total),
            static_cast<double>(smallest_cohort) / max(1, largest_cohort),
            clamp(schedule_cost_ / max(1e-12, merged_post), 4.0) / 4.0,
            clamp(savings / max(1e-12, merged_post), 8.0) / 8.0,
            clamp(transfer_time(static_cast<long long>(total) * bytes_per_token_) /
                      max(1e-12, savings), 4.0) / 4.0,
            clamp(ready_dispersion / max(1e-12, savings), 2.0) / 2.0,
            efficiency(DurationColumn::DECODE_PRE),
            efficiency(DurationColumn::DECODE_PROC),
            efficiency(DurationColumn::DECODE_POST),
            clamp(token_transfer / max(1e-12, schedule_cost_), 8.0) / 8.0,
            clamp(static_cast<double>(pending_up_transfers_) / max(1, total), 2.0) / 2.0,
            clamp(static_cast<double>(pending_down_transfers_) / max(1, total), 2.0) / 2.0,
            clamp(log1p(produced_mean) / log(257.0), 1.5),
            clamp(sqrt(produced_variance) / max(1.0, produced_mean), 4.0) / 4.0,
            clamp(oldest_age / max(1e-12, slo_tpot_), 4.0) / 4.0,
            clamp(throughput_upper_bound_ / max(1e-12, throughput_baseline_), 20.0) / 20.0,
        };
    }
    // SUBMISSION_FEATURE_END learned_policy

    bool dynamic_coherent_dpost_enabled(const vector<int>& members) const {
        if constexpr (!DYNAMIC_COHERENT_DPOST || kOptimizationLevel < 20) {
            return false;
        }
        const int total = static_cast<int>(members.size());
        if (throughput_weight_ < 0.95 || total < 2 ||
            total != total_active_decode_requests_ ||
            best_group_size(DurationColumn::DECODE_POST, total) != total) {
            return false;
        }
        int known_unfinished = 0;
        for (const Request& req : requests_) {
            if (req.state != RequestState::UNSEEN && req.state != RequestState::FINISHED) {
                ++known_unfinished;
            }
        }
        if (known_unfinished != total) {
            return false;
        }
        vector<int> per_cloud(cloud_count_, 0);
        for (int request_id : members) {
            ++per_cloud[request(request_id).cloud];
        }
        int fanout = 0;
        double separate_post = 0.0;
        double earliest_ready = numeric_limits<double>::infinity();
        double latest_ready = 0.0;
        double up_tail = max(predicted_up_tail_, edge_busy_until_);
        for (int cloud = 0; cloud < cloud_count_; ++cloud) {
            const int count = per_cloud[cloud];
            if (count == 0) {
                continue;
            }
            ++fanout;
            separate_post += schedule_cost_ +
                             duration(DurationColumn::DECODE_POST, count);
            up_tail += transfer_time(
                static_cast<long long>(count) * bytes_per_token_
            );
            const double cloud_ready = max(
                up_tail, cloud_busy_[cloud] ? cloud_busy_until_[cloud] : current_time_
            );
            const double post_ready = cloud_ready + schedule_cost_ +
                duration(DurationColumn::DECODE_PROC, count) +
                transfer_time(static_cast<long long>(count) * bytes_per_token_);
            earliest_ready = min(earliest_ready, post_ready);
            latest_ready = max(latest_ready, post_ready);
        }
        if (fanout < 2) {
            return false;
        }
        const double merged_post = schedule_cost_ +
                                   duration(DurationColumn::DECODE_POST, total);
        const double savings = separate_post - merged_post;
        const double ready_dispersion = latest_ready - earliest_ready;
        if (savings < 0.5 * merged_post ||
            transfer_time(static_cast<long long>(total) * bytes_per_token_) >
                savings + 1e-12) {
            return false;
        }
        // SUBMISSION_FEATURE_BEGIN learned_policy_training
        if constexpr (LEARNED_POLICY_TRACE) {
            const bool fallback_acts = total <= 8 &&
                ready_dispersion <= 0.15 * savings + 1e-12;
            const bool widest_action_acts = total <= 256 &&
                ready_dispersion <= 2.0 * savings + 1e-12;
            if (!learned_policy_trace_emitted_ && widest_action_acts && !fallback_acts) {
                learned_policy_trace_emitted_ = true;
                cerr << "LP1";
                for (double feature : learned_policy_features(
                         total, per_cloud, fanout, merged_post, savings, ready_dispersion
                     )) {
                    cerr << ' ' << feature;
                }
                cerr << '\n';
            }
        }
        // SUBMISSION_FEATURE_END learned_policy_training
        int maximum_group = DYNAMIC_COHERENT_MAX_GROUP;
        double dispersion_ratio = DYNAMIC_COHERENT_DISPERSION_RATIO;
        // SUBMISSION_FEATURE_BEGIN learned_policy
        if constexpr (LEARNED_POLICY) {
            const bool fallback_acts = total <= 8 &&
                ready_dispersion <= 0.15 * savings + 1e-12;
            const bool widest_action_acts = total <= 256 &&
                ready_dispersion <= 2.0 * savings + 1e-12;
            if (learned_policy_action_ == -2 && widest_action_acts && !fallback_acts) {
                learned_policy_action_ = learned_policy_action(learned_policy_features(
                    total, per_cloud, fanout, merged_post, savings, ready_dispersion
                ));
            }
            maximum_group = learned_policy_action_ >= 0 ? 256 : 8;
            static constexpr double ratios[6] = {0.15,0.25,0.4,0.5,0.75,1.0};
            dispersion_ratio = learned_policy_action_ >= 0
                ? ratios[learned_policy_action_]
                : 0.15;
        }
        // SUBMISSION_FEATURE_END learned_policy
        return total <= maximum_group &&
               ready_dispersion <=
                   dispersion_ratio * savings + 1e-12;
    }
    // SUBMISSION_FEATURE_END dynamic_coherent_dpost

    // SUBMISSION_FEATURE_BEGIN ppost_cohort_seed
    bool completes_small_decode_cohort(const Candidate& candidate) const {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (!PPOST_COHORT_SEED || kOptimizationLevel < 20) {
            return false;
        }
        // SUBMISSION_FEATURE_END pre20_only
        if (candidate.kind != TaskKind::P_POST || throughput_weight_ < 0.95 ||
            cloud_count_ < 2 || p_post_ready_.size() != 1 || d_pre_ready_.empty() ||
            int(d_pre_ready_.size()) != total_active_decode_requests_ ||
            !d_post_ready_.empty()) {
            return false;
        }
        const int size = int(d_pre_ready_.size()) + 1;
        return best_group_size(DurationColumn::DECODE_PRE, size) == size &&
               schedule_cost_ + duration(DurationColumn::DECODE_PRE, size) <=
                   0.98 * (2.0 * schedule_cost_ +
                           duration(DurationColumn::DECODE_PRE, size - 1) +
                           duration(DurationColumn::DECODE_PRE, 1));
    }
    // SUBMISSION_FEATURE_END ppost_cohort_seed

    // SUBMISSION_FEATURE_BEGIN prefill_cohort_wait
    bool should_wait_for_prefill_cohort() {
        if constexpr (!PREFILL_COHORT_WAIT) {
            return false;
        }
        if (throughput_weight_ < 0.95 || cloud_count_ < 2 ||
            d_pre_ready_.size() != 1 || total_active_decode_requests_ != 1 ||
            !p_post_ready_.empty() || !d_post_ready_.empty()) {
            return false;
        }
        const Request& current = request(
            queue_front(d_pre_ready_, RequestState::READY_D_PRE)
        );
        const Request* future = nullptr;
        double future_ready_time = numeric_limits<double>::infinity();
        for (const Request& req : requests_) {
            if (req.cloud != current.cloud) {
                continue;
            }
            double ready_time = numeric_limits<double>::infinity();
            if (req.state == RequestState::RUNNING_P_PROC &&
                req.running_prefill_layer_end == layer_count_) {
                ready_time = max(
                    cloud_busy_until_[req.cloud], predicted_down_tail_
                ) + transfer_time(
                    static_cast<long long>(req.input_length) * bytes_per_token_
                );
            } else if (req.state == RequestState::WAITING_PREFILL_DOWN) {
                const long long bytes =
                    static_cast<long long>(req.input_length) * bytes_per_token_;
                for (const TransferPrediction& transfer : predicted_down_queue_) {
                    if (!transfer.decode && transfer.remote == req.cloud &&
                        transfer.size_bytes == bytes) {
                        ready_time = transfer.finish_time;
                        break;
                    }
                }
            }
            if (!isfinite(ready_time)) {
                continue;
            }
            if (future != nullptr) {
                return false;
            }
            future = &req;
            future_ready_time = ready_time;
        }
        if (future == nullptr || future_ready_time < current_time_ - 1e-12) {
            return false;
        }
        const double wait = future_ready_time - current_time_;
        if (wait > 0.2 * schedule_cost_ + 1e-12 ||
            best_group_size(DurationColumn::DECODE_PRE, 2) != 2 ||
            best_group_size(DurationColumn::DECODE_PROC, 2) != 2 ||
            best_group_size(DurationColumn::DECODE_POST, 2) != 2) {
            return false;
        }
        const double merged_path =
            3.0 * schedule_cost_ +
            duration(DurationColumn::DECODE_PRE, 2) +
            duration(DurationColumn::DECODE_PROC, 2) +
            duration(DurationColumn::DECODE_POST, 2);
        const double split_path = 2.0 * (
            3.0 * schedule_cost_ +
            duration(DurationColumn::DECODE_PRE, 1) +
            duration(DurationColumn::DECODE_PROC, 1) +
            duration(DurationColumn::DECODE_POST, 1)
        );
        return wait + schedule_cost_ +
                   duration(DurationColumn::PREFILL_POST, future->input_length) +
                   merged_path <= 0.75 * split_path + 1e-12;
    }
    // SUBMISSION_FEATURE_END prefill_cohort_wait

    // SUBMISSION_FEATURE_BEGIN initial_decode_barrier
    bool should_hold_initial_decode_frontier() const {
        if constexpr (!INITIAL_DECODE_BARRIER || kOptimizationLevel < 20) {
            return false;
        }
        const int ready = static_cast<int>(d_pre_ready_.size());
        if (throughput_weight_ < 0.5 || cloud_count_ < 2 || ready == 0 ||
            ready != total_active_decode_requests_ ||
            ready > INITIAL_DECODE_MAX_READY_FRACTION * requests_.size() ||
            latency_ms_ < INITIAL_DECODE_MIN_LATENCY_S_RATIO * schedule_cost_) {
            return false;
        }
        int prefill = 0;
        int known = 0;
        vector<int> cloud_members(cloud_count_, 0);
        for (const Request& req : requests_) {
            if (req.state == RequestState::UNSEEN || req.state == RequestState::FINISHED) {
                continue;
            }
            ++known;
            if (req.produced_tokens != 0) {
                return false;
            }
            if (req.state == RequestState::READY_D_PRE) {
                if (req.cloud < 0) {
                    return false;
                }
                ++cloud_members[req.cloud];
                continue;
            }
            if (req.state < RequestState::READY_D_PRE) {
                if (req.cloud < 0) {
                    return false;
                }
                ++prefill;
                ++cloud_members[req.cloud];
                continue;
            }
            return false;
        }
        if (prefill == 0 || known < 4 || known > 64 ||
            best_group_size(DurationColumn::DECODE_PRE, known) != known ||
            best_group_size(DurationColumn::DECODE_POST, known) != known) {
            return false;
        }
        for (int count : cloud_members) {
            if (count > 0 && best_group_size(DurationColumn::DECODE_PROC, count) != count) {
                return false;
            }
        }
        if constexpr (INITIAL_DECODE_REQUIRE_MONOTONIC) {
            for (int column = static_cast<int>(DurationColumn::DECODE_PRE);
                 column <= static_cast<int>(DurationColumn::DECODE_POST); ++column) {
                const auto& curve = duration_curves_[column];
                for (size_t index = 1; index < curve.size(); ++index) {
                    if (curve[index].second + 1e-12 < curve[index - 1].second) {
                        return false;
                    }
                }
            }
        }
        double savings = known * (schedule_cost_ + duration(DurationColumn::DECODE_PRE, 1)) -
                         schedule_cost_ - duration(DurationColumn::DECODE_PRE, known) +
                         known * (schedule_cost_ + duration(DurationColumn::DECODE_POST, 1)) -
                         schedule_cost_ - duration(DurationColumn::DECODE_POST, known);
        for (int count : cloud_members) {
            if (count > 0) {
                savings += count * (schedule_cost_ + duration(DurationColumn::DECODE_PROC, 1)) -
                           schedule_cost_ - duration(DurationColumn::DECODE_PROC, count);
            }
        }
        if (savings + 1e-12 < INITIAL_DECODE_MIN_SAVINGS_TRANSFERS *
                                 transfer_time(bytes_per_token_)) {
            return false;
        }
        return true;
    }
    // SUBMISSION_FEATURE_END initial_decode_barrier

    bool score_aware_candidate_less(const Candidate& left, const Candidate& right) const {
        // SUBMISSION_FEATURE_BEGIN ppost_cohort_seed
        const bool left_completes_cohort = completes_small_decode_cohort(left);
        const bool right_completes_cohort = completes_small_decode_cohort(right);
        if (left_completes_cohort != right_completes_cohort) {
            return left_completes_cohort;
        }
        // SUBMISSION_FEATURE_END ppost_cohort_seed
        const bool use_deadlines = latency_weight_ > 0.8;
        const bool left_overdue = use_deadlines && left.urgency >= 1.0;
        const bool right_overdue = use_deadlines && right.urgency >= 1.0;
        if (left_overdue != right_overdue) {
            return left_overdue;
        }
        if (left_overdue) {
            const double left_priority = left.action_value +
                                         0.001 * (3 - left.stage_rank);
            const double right_priority = right.action_value +
                                          0.001 * (3 - right.stage_rank);
            if (abs(left_priority - right_priority) > 1e-12) {
                return left_priority > right_priority;
            }
        }
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 14) {
        // SUBMISSION_FEATURE_END pre20_only
            const double normalized_pressure = max(
                predicted_link_delay("UP") / max(1e-9, slo_tdr_),
                predicted_link_delay("DOWN") / max(1e-9, slo_tpot_)
            );
            // SUBMISSION_FEATURE_BEGIN pre20_only
            if constexpr (kBackpressureOlderPProc && kOptimizationLevel >= 20) {
            // SUBMISSION_FEATURE_END pre20_only
                const bool proc_pair =
                    (left.kind == TaskKind::P_PROC && right.kind == TaskKind::D_PROC) ||
                    (left.kind == TaskKind::D_PROC && right.kind == TaskKind::P_PROC);
                if (normalized_pressure > 1.0 && proc_pair &&
                    left.sequence != right.sequence) {
                    const Candidate& older = left.sequence < right.sequence ? left : right;
                    const Request& prefill_req = request(older.request_id);
                    const double prefill_service = schedule_cost_ + duration(
                        DurationColumn::PREFILL_PROC, prefill_req.input_length
                    );
                    const double decode_service = schedule_cost_ + duration(
                        DurationColumn::DECODE_PROC, 1
                    );
                    if (older.kind == TaskKind::P_PROC &&
                        prefill_req.next_prefill_layer > 0 && latency_weight_ >= 0.75 &&
                        prefill_service >= 4.0 * decode_service) {
                        return left.sequence < right.sequence;
                    }
                }
            // SUBMISSION_FEATURE_BEGIN pre20_only
            }
            // SUBMISSION_FEATURE_END pre20_only
            if (normalized_pressure > 1.0 &&
                abs(left.action_value - right.action_value) > 1e-12) {
                return left.action_value > right.action_value;
            }
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        if (left.sequence != right.sequence) {
            return left.sequence < right.sequence;
        }
        return left.stage_rank < right.stage_rank;
    }

    // SUBMISSION_FEATURE_BEGIN objective_margin_rollout
    int rollout_group_size(const Candidate& candidate) const {
        if (candidate.kind == TaskKind::D_PRE) {
            return best_group_size(
                DurationColumn::DECODE_PRE, static_cast<int>(d_pre_ready_.size())
            );
        }
        if (candidate.kind == TaskKind::D_POST) {
            return best_group_size(
                DurationColumn::DECODE_POST, static_cast<int>(d_post_ready_.size())
            );
        }
        if (candidate.kind == TaskKind::D_PROC) {
            const int cloud = request(candidate.request_id).cloud;
            return best_group_size(
                DurationColumn::DECODE_PROC,
                static_cast<int>(d_proc_ready_[cloud].size())
            );
        }
        return 1;
    }

    double rollout_candidate_value(const Candidate& candidate, double start_delay) const {
        const Request& req = request(candidate.request_id);
        const int group_size = rollout_group_size(candidate);
        const double service = action_service_time(candidate.kind, group_size, req);
        const bool prefill = candidate.kind == TaskKind::P_PRE ||
                             candidate.kind == TaskKind::P_PROC ||
                             candidate.kind == TaskKind::P_POST;
        const double milestone = prefill
            ? estimated_prefill_path(candidate.kind, req)
            : estimated_decode_path(candidate.kind, group_size);
        const double observed = prefill
            ? current_time_ - req.arrival_time
            : current_time_ - req.decode_clock_start;
        const double slo = prefill ? slo_tdr_ : slo_tpot_;
        const double ratio = (observed + start_delay + milestone) / max(1e-9, slo);
        const double excess = max(0.0, ratio - 1.0);
        const double latency_quality = distance_baseline_ > 0
            ? max(0.0, 1.0 - excess / distance_baseline_)
            : 1.0 / (1.0 + excess);
        const double rate_reference = max(
            1e-9, max(throughput_upper_bound_, throughput_baseline_)
        );
        const double rate_quality = min(
            4.0, group_size / max(1e-9, service) / rate_reference
        );
        double progress = 0.75;
        if (candidate.kind == TaskKind::P_POST || candidate.kind == TaskKind::D_POST) {
            progress = 1.5;
        } else if (candidate.kind == TaskKind::P_PROC ||
                   candidate.kind == TaskKind::D_PROC) {
            progress = 1.0;
        }
        return throughput_weight_ * rate_quality +
               latency_weight_ * progress * latency_quality;
    }

    void apply_objective_margin_rollout(vector<Candidate>& candidates) const {
        const int horizon = min<int>(3, candidates.size());
        if (!OBJECTIVE_MARGIN_ROLLOUT || horizon < 2) {
            return;
        }
        bool consequential = false;
        for (const Candidate& candidate : candidates) {
            consequential = consequential ||
                candidate.urgency >= OBJECTIVE_MARGIN_MIN_URGENCY;
        }
        if (latency_weight_ < OBJECTIVE_MARGIN_MIN_LATENCY_WEIGHT || !consequential) {
            return;
        }
        auto sequence_value = [&](const vector<int>& order) {
            double start_delay = 0.0;
            double value = 0.0;
            for (int position = 0; position < horizon; ++position) {
                const Candidate& candidate = candidates[order[position]];
                value += rollout_candidate_value(candidate, start_delay) /
                         (position + 1.0);
                const Request& req = request(candidate.request_id);
                start_delay += action_service_time(
                    candidate.kind, rollout_group_size(candidate), req
                );
            }
            return value;
        };

        vector<int> fallback(horizon);
        for (int index = 0; index < horizon; ++index) {
            fallback[index] = index;
        }
        vector<int> best_order = fallback;
        double best_value = sequence_value(fallback);
        vector<int> order = fallback;
        while (next_permutation(order.begin(), order.end())) {
            const double value = sequence_value(order);
            if (value > best_value + OBJECTIVE_MARGIN_ROLLOUT_THRESHOLD) {
                best_value = value;
                best_order = order;
            }
        }
        if (best_order == fallback) {
            return;
        }
        vector<Candidate> reordered;
        reordered.reserve(candidates.size());
        for (int index : best_order) {
            reordered.push_back(candidates[index]);
        }
        for (int index = horizon; index < static_cast<int>(candidates.size()); ++index) {
            reordered.push_back(candidates[index]);
        }
        candidates = std::move(reordered);
    }
    // SUBMISSION_FEATURE_END objective_margin_rollout

    vector<Candidate> edge_candidates() {
        vector<Candidate> candidates;
        auto add = [&](TaskKind kind, deque<int>& queue, RequestState expected) {
            // SUBMISSION_FEATURE_BEGIN pre20_only
            if constexpr (COHERENT_DECODE_BATCH && kOptimizationLevel >= 20) {
            // SUBMISSION_FEATURE_END pre20_only
                if (kind == TaskKind::D_PRE && !coherent_decode_batch_.empty()) {
                    return;
                }
            // SUBMISSION_FEATURE_BEGIN pre20_only
            }
            // SUBMISSION_FEATURE_END pre20_only
            if (!queue_available(queue, expected)) {
                return;
            }
            const int request_id = queue.front();
            const Request& req = request(request_id);
            int group_size = 1;
            if (kind == TaskKind::D_PRE || kind == TaskKind::D_POST) {
                group_size = best_group_size(
                    kind == TaskKind::D_PRE
                        ? DurationColumn::DECODE_PRE
                        : DurationColumn::DECODE_POST,
                    static_cast<int>(queue.size())
                );
            }
            candidates.push_back(
                {kind, request_id, req.ready_sequence, request_urgency(kind, req),
                 edge_stage_rank(kind), action_value(kind, req, group_size)}
            );
        };
        add(TaskKind::P_PRE, p_pre_ready_, RequestState::READY_P_PRE);
        add(TaskKind::P_POST, p_post_ready_, RequestState::READY_P_POST);
        add(TaskKind::D_PRE, d_pre_ready_, RequestState::READY_D_PRE);
        add(TaskKind::D_POST, d_post_ready_, RequestState::READY_D_POST);

        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 11) {
        // SUBMISSION_FEATURE_END pre20_only
            stable_sort(candidates.begin(), candidates.end(), [this](const Candidate& left, const Candidate& right) {
                return score_aware_candidate_less(left, right);
            });
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        // SUBMISSION_FEATURE_BEGIN legacy_priority
        else if constexpr (kOptimizationLevel < 5) {
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
        if constexpr (kOptimizationLevel >= 7 && kOptimizationLevel < 11) {
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
        // SUBMISSION_FEATURE_END legacy_priority
        // SUBMISSION_FEATURE_BEGIN edge_stage_restore
        if constexpr (EDGE_STAGE_PRIORITY_RESTORE && kOptimizationLevel >= 20) {
            bool link_constrained = false;
            if (cloud_count_ == 1 && requests_.size() <= 16 &&
                throughput_weight_ >= 0.2 && latency_weight_ >= 0.5 &&
                schedule_cost_ >= duration(DurationColumn::DECODE_PRE, 1) +
                                      duration(DurationColumn::DECODE_PROC, 1) +
                                      duration(DurationColumn::DECODE_POST, 1) &&
                queue_available(p_pre_ready_, RequestState::READY_P_PRE)) {
                const Request& pending = request(p_pre_ready_.front());
                link_constrained = bandwidth_gbps_ >= 0.1 &&
                    transfer_time(static_cast<long long>(pending.input_length) * bytes_per_token_) >
                        slo_tpot_;
            }
            if (link_constrained) {
                stable_sort(
                    candidates.begin(), candidates.end(),
                    [](const Candidate& left, const Candidate& right) {
                        return left.stage_rank < right.stage_rank;
                    }
                );
            }
        }
        // SUBMISSION_FEATURE_END edge_stage_restore
        // SUBMISSION_FEATURE_BEGIN objective_margin_rollout
        if constexpr (OBJECTIVE_MARGIN_ROLLOUT) {
            apply_objective_margin_rollout(candidates);
        }
        // SUBMISSION_FEATURE_END objective_margin_rollout
        return candidates;
    }

    int best_group_size(DurationColumn column, int available) const {
        if (available <= 1 || kOptimizationLevel < 3) {
            return 1;
        }
        // SUBMISSION_FEATURE_BEGIN experimental_grouping
        if constexpr (kExperimentalGrouping) {
            const vector<int>& cache = best_group_size_cache_[static_cast<int>(column)];
            return cache[min<int>(available, cache.size() - 1)];
        }
        // SUBMISSION_FEATURE_END experimental_grouping
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel == 3) {
            return available;
        }
        // SUBMISSION_FEATURE_END pre20_only

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
            // SUBMISSION_FEATURE_BEGIN pre20_only
            if constexpr (kOptimizationLevel >= 7) {
            // SUBMISSION_FEATURE_END pre20_only
                if (column == DurationColumn::DECODE_PRE ||
                    column == DurationColumn::DECODE_PROC) {
                    service_time += transfer_time(
                        static_cast<long long>(size) * bytes_per_token_
                    );
                }
            // SUBMISSION_FEATURE_BEGIN pre20_only
            }
            // SUBMISSION_FEATURE_END pre20_only
            // SUBMISSION_FEATURE_BEGIN pre20_only
            if constexpr (kOptimizationLevel >= 15) {
            // SUBMISSION_FEATURE_END pre20_only
                if (column == DurationColumn::DECODE_PRE &&
                    downstream_group_is_hostile(size)) {
                    service_time += schedule_cost_ +
                                    duration(DurationColumn::DECODE_PROC, size) +
                                    transfer_time(
                                        static_cast<long long>(size) * bytes_per_token_
                                    ) +
                                    schedule_cost_ +
                                    duration(DurationColumn::DECODE_POST, size);
                } else if (column == DurationColumn::DECODE_PROC &&
                           downstream_group_is_hostile(size)) {
                    service_time += schedule_cost_ +
                                    duration(DurationColumn::DECODE_POST, size);
                }
            // SUBMISSION_FEATURE_BEGIN pre20_only
            }
            // SUBMISSION_FEATURE_END pre20_only
            const double rate = size / service_time;
            if (rate > best_rate + 1e-12 ||
                (abs(rate - best_rate) <= 1e-12 && size < best_size)) {
                best_rate = rate;
                best_size = size;
            }
        }
        return best_size;
    }

    // SUBMISSION_FEATURE_BEGIN experimental_grouping
    vector<int> bounded_candidate_group_sizes(
        DurationColumn column,
        int available
    ) const {
        set<int> sizes = {1, available};
        const int best = best_group_size(column, available);
        for (int candidate : {
                 best - 1,
                 best,
                 best + 1,
                 best / 2,
                 min(available, 2 * best),
                 available / 4,
                 available / 2,
                 3 * available / 4,
             }) {
            if (1 <= candidate && candidate <= available) {
                sizes.insert(candidate);
            }
        }

        const vector<pair<int, double>>& curve =
            duration_curves_[static_cast<int>(column)];
        auto near_best = lower_bound(
            curve.begin(), curve.end(), make_pair(best, -numeric_limits<double>::infinity())
        );
        for (int offset = -2; offset <= 2; ++offset) {
            const long long index = distance(curve.begin(), near_best) + offset;
            if (0 <= index && index < static_cast<long long>(curve.size())) {
                const int candidate = min(available, curve[index].first);
                if (candidate >= 1) {
                    sizes.insert(candidate);
                }
            }
        }
        return vector<int>(sizes.begin(), sizes.end());
    }

    GroupEvaluation evaluate_decode_group(
        TaskKind kind,
        DurationColumn column,
        const vector<int>& group,
        const vector<int>& all_ready
    ) const {
        GroupEvaluation result;
        const int size = static_cast<int>(group.size());
        vector<int> counts(cloud_count_, 0);
        for (int request_id : group) {
            ++counts[request(request_id).cloud];
        }
        result.fanout = count_if(counts.begin(), counts.end(), [](int count) {
            return count > 0;
        });

        const double stage_service = schedule_cost_ + duration(column, size);
        double earliest_down_finish = numeric_limits<double>::infinity();
        double latest_down_finish = current_time_;

        if (kind == TaskKind::D_POST) {
            result.token_finish = current_time_ + stage_service;
        } else if (kind == TaskKind::D_PROC) {
            const double process_finish = current_time_ + stage_service;
            const double down_finish = max(process_finish, predicted_down_tail_) +
                                       transfer_time(
                                           static_cast<long long>(size) * bytes_per_token_
                                       );
            earliest_down_finish = latest_down_finish = down_finish;
            result.token_finish = max(down_finish, edge_busy_until_) + schedule_cost_ +
                                  duration(DurationColumn::DECODE_POST, size);
        } else {
            const double edge_finish = current_time_ + stage_service;
            double up_tail = max(edge_finish, predicted_up_tail_);
            vector<pair<double, int>> process_cohorts;
            for (int cloud = 0; cloud < cloud_count_; ++cloud) {
                if (counts[cloud] == 0) {
                    continue;
                }
                up_tail += transfer_time(
                    static_cast<long long>(counts[cloud]) * bytes_per_token_
                );
                const double process_finish =
                    max(up_tail, cloud_busy_until_[cloud]) + schedule_cost_ +
                    duration(DurationColumn::DECODE_PROC, counts[cloud]);
                process_cohorts.push_back({process_finish, cloud});
            }
            sort(process_cohorts.begin(), process_cohorts.end());

            double down_tail = max(current_time_, predicted_down_tail_);
            for (const auto& [process_finish, cloud] : process_cohorts) {
                down_tail = max(down_tail, process_finish) + transfer_time(
                    static_cast<long long>(counts[cloud]) * bytes_per_token_
                );
                earliest_down_finish = min(earliest_down_finish, down_tail);
                latest_down_finish = max(latest_down_finish, down_tail);
            }
            result.token_finish = max(down_tail, edge_finish) + schedule_cost_ +
                                  duration(DurationColumn::DECODE_POST, size);
        }

        result.horizon = max(1e-9, result.token_finish - current_time_);
        const double rate = size / result.horizon;
        const double rate_reference = max(
            1e-9,
            max(throughput_upper_bound_, throughput_baseline_)
        );
        result.normalized_rate = min(4.0, rate / rate_reference);

        const double singleton_service = schedule_cost_ + duration(column, 1);
        result.service_efficiency = max(
            -2.0,
            min(
                1.0,
                1.0 - stage_service / max(1e-9, size * singleton_service)
            )
        );

        double gap_sum = 0;
        double urgency_sum = 0;
        double completion_sum = 0;
        for (int request_id : group) {
            const Request& req = request(request_id);
            gap_sum += max(0.0, result.token_finish - req.decode_clock_start);
            urgency_sum += request_urgency(kind, req);
            completion_sum += 1.0 / max(1.0, expected_remaining_tokens(req));
        }
        const double mean_gap = gap_sum / size;
        const double gap_ratio = mean_gap / max(1e-9, slo_tpot_);
        const double excess_gap = max(0.0, gap_ratio - 1.0);
        result.waiting_quality = distance_baseline_ > 0
            ? max(0.0, 1.0 - excess_gap / distance_baseline_)
            : (excess_gap <= 1e-12 ? 1.0 : 0.0);
        const double mean_urgency = urgency_sum / size;
        result.urgency_progress = min(
            4.0,
            mean_urgency / max(1.0, result.horizon / max(1e-9, slo_tpot_))
        );
        result.completion_potential = completion_sum / size;

        vector<char> included(requests_.size(), false);
        for (int request_id : group) {
            included[request_id] = true;
        }
        double most_urgent_excluded = 0;
        for (int request_id : all_ready) {
            if (!included[request_id]) {
                most_urgent_excluded = max(
                    most_urgent_excluded,
                    request_urgency(kind, request(request_id))
                );
            }
        }
        result.excluded_pressure = min(
            4.0,
            most_urgent_excluded * stage_service / max(1e-9, slo_tpot_)
        );

        const double active_link_delay =
            predicted_link_delay("UP") + predicted_link_delay("DOWN");
        result.link_pressure = min(
            4.0,
            active_link_delay / max(1e-9, slo_tpot_)
        );
        result.fanout_pressure = kind == TaskKind::D_PRE
            ? max(0, result.fanout - 1) *
                  transfer_time(bytes_per_token_) / max(1e-9, slo_tpot_)
            : 0.0;
        if (kind == TaskKind::D_PRE && result.fanout > 1) {
            const int largest_cloud_cohort = *max_element(counts.begin(), counts.end());
            const double fragmentation =
                1.0 - static_cast<double>(largest_cloud_cohort) / size;
            result.fanout_pressure += fragmentation * (1.0 + result.link_pressure);
        }
        if (isfinite(earliest_down_finish)) {
            result.finish_dispersion = max(
                0.0,
                (latest_down_finish - earliest_down_finish) / max(1e-9, slo_tpot_)
            );
        }
        return result;
    }

    double counterfactual_group_value(const GroupEvaluation& group) const {
        double rate_weight = 1.15;
        double efficiency_weight = 0.40;
        double waiting_weight = 1.00;
        double urgency_weight = 0.40;
        double completion_weight = 0.10;
        double fanout_penalty = 0.20;
        double excluded_penalty = 0.28;
        double dispersion_penalty = 0.15;
        if constexpr (kOptimizationLevel >= 17) {
            rate_weight = GROUP_RATE_WEIGHT;
            efficiency_weight = GROUP_EFFICIENCY_WEIGHT;
            waiting_weight = GROUP_LATENCY_WEIGHT;
            urgency_weight = GROUP_URGENCY_WEIGHT;
            completion_weight = GROUP_COMPLETION_WEIGHT;
            fanout_penalty = GROUP_FANOUT_PENALTY;
            excluded_penalty = GROUP_EXCLUDED_PENALTY;
            dispersion_penalty = GROUP_DISPERSION_PENALTY;
        }

        double value =
            throughput_weight_ *
                (rate_weight * group.normalized_rate +
                 efficiency_weight * group.service_efficiency) +
            latency_weight_ *
                (waiting_weight * group.waiting_quality +
                 urgency_weight * group.urgency_progress +
                 completion_weight * group.completion_potential) -
            fanout_penalty * group.fanout_pressure -
            excluded_penalty * group.excluded_pressure -
            dispersion_penalty * group.finish_dispersion;

        if constexpr (kOptimizationLevel >= 18) {
            const double uncongested = max(0.0, 1.0 - group.link_pressure);
            value += GROUP_INTERACTION_EFFICIENCY * throughput_weight_ *
                     group.service_efficiency * uncongested;
            value += GROUP_INTERACTION_URGENCY * latency_weight_ *
                     group.urgency_progress * (1.0 - group.waiting_quality);
            value -= GROUP_INTERACTION_CONGESTION *
                     (group.fanout_pressure * group.link_pressure +
                      group.excluded_pressure * max(0.0, group.urgency_progress - 1.0));
        }
        return value;
    }

    vector<int> choose_counterfactual_decode_group(
        deque<int>& queue,
        RequestState expected,
        TaskKind kind,
        DurationColumn column,
        bool add_cloud_packing,
        const vector<int>& fallback_group
    ) {
        vector<int> ready = collect_ready(queue, expected);
        if (ready.empty()) {
            fail("counterfactual grouping found no ready members");
        }
        if (ready.size() == 1) {
            return ready;
        }

        vector<int> by_urgency = ready;
        stable_sort(by_urgency.begin(), by_urgency.end(), [&](int left, int right) {
            const double left_value = request_urgency(kind, request(left));
            const double right_value = request_urgency(kind, request(right));
            if (abs(left_value - right_value) > 1e-12) {
                return left_value > right_value;
            }
            return request(left).ready_sequence < request(right).ready_sequence;
        });

        vector<int> by_member_value = ready;
        stable_sort(by_member_value.begin(), by_member_value.end(), [&](int left, int right) {
            const double left_value = decode_member_value(request(left), kind);
            const double right_value = decode_member_value(request(right), kind);
            if (abs(left_value - right_value) > 1e-12) {
                return left_value > right_value;
            }
            return request(left).ready_sequence < request(right).ready_sequence;
        });

        map<int, vector<int>> by_cloud;
        if (add_cloud_packing) {
            for (int request_id : by_member_value) {
                by_cloud[request(request_id).cloud].push_back(request_id);
            }
        }

        vector<vector<int>> candidates;
        const vector<int> sizes = bounded_candidate_group_sizes(column, ready.size());
        auto add_prefix = [&](const vector<int>& order, int size) {
            candidates.emplace_back(order.begin(), order.begin() + size);
        };
        for (int size : sizes) {
            add_prefix(ready, size);
            add_prefix(by_urgency, size);
            add_prefix(by_member_value, size);

            if (!add_cloud_packing) {
                continue;
            }
            for (const auto& [anchor_cloud, anchor_members] : by_cloud) {
                vector<int> packed;
                packed.reserve(size);
                for (int request_id : anchor_members) {
                    if (static_cast<int>(packed.size()) == size) {
                        break;
                    }
                    packed.push_back(request_id);
                }
                vector<pair<int, int>> remaining_clouds;
                for (const auto& [cloud, members] : by_cloud) {
                    if (cloud != anchor_cloud) {
                        remaining_clouds.push_back(
                            {-static_cast<int>(members.size()), cloud}
                        );
                    }
                }
                sort(remaining_clouds.begin(), remaining_clouds.end());
                for (const auto& [ignored_size, cloud] : remaining_clouds) {
                    (void)ignored_size;
                    for (int request_id : by_cloud[cloud]) {
                        if (static_cast<int>(packed.size()) == size) {
                            break;
                        }
                        packed.push_back(request_id);
                    }
                    if (static_cast<int>(packed.size()) == size) {
                        break;
                    }
                }
                if (static_cast<int>(packed.size()) == size) {
                    candidates.push_back(std::move(packed));
                }
            }
        }

        vector<int> best_group = fallback_group;
        if (best_group.empty()) {
            best_group = {ready.front()};
        }
        GroupEvaluation best_evaluation = evaluate_decode_group(
            kind, column, best_group, ready
        );
        const GroupEvaluation fallback_evaluation = best_evaluation;
        double best_value = counterfactual_group_value(best_evaluation);
        const double fallback_value = best_value;
        set<vector<int>> seen;
        for (vector<int>& candidate : candidates) {
            vector<int> identity = candidate;
            sort(identity.begin(), identity.end());
            if (!seen.insert(identity).second) {
                continue;
            }
            const GroupEvaluation evaluation = evaluate_decode_group(
                kind, column, candidate, ready
            );
            if (add_cloud_packing &&
                evaluation.fanout > fallback_evaluation.fanout) {
                continue;
            }
            const double value = counterfactual_group_value(evaluation);
            const bool better_tie =
                evaluation.fanout < best_evaluation.fanout ||
                (evaluation.fanout == best_evaluation.fanout &&
                 ((throughput_weight_ >= latency_weight_ &&
                   candidate.size() > best_group.size()) ||
                  (throughput_weight_ < latency_weight_ &&
                   candidate.size() < best_group.size())));
            if (value > best_value + 1e-12 ||
                (abs(value - best_value) <= 1e-12 && better_tie)) {
                best_value = value;
                best_evaluation = evaluation;
                best_group = candidate;
            }
        }
        const double minimum_margin = kOptimizationLevel >= 17
            ? GROUP_DECISION_MARGIN
            : 0.04;
        if (best_value < fallback_value + minimum_margin) {
            return fallback_group;
        }
        return best_group;
    }
    // SUBMISSION_FEATURE_END experimental_grouping

    // SUBMISSION_FEATURE_BEGIN exact_dpost_partition
    int exact_dpost_partition_first(const vector<int>& ready) const {
        const int count = static_cast<int>(ready.size());
        if (count <= 1) {
            return count;
        }
        vector<double> suffix_weight(count + 1, 0.0);
        for (int index = count - 1; index >= 0; --index) {
            const Request& req = request(ready[index]);
            const double urgency = observed_request_urgency(TaskKind::D_POST, req);
            suffix_weight[index] = suffix_weight[index + 1] + 1.0 +
                4.0 * max(0.0, urgency - 1.0) +
                1.0 / max(1.0, expected_remaining_tokens(req));
        }

        vector<double> best(count + 1, numeric_limits<double>::infinity());
        vector<int> first(count + 1, 0);
        best[0] = 0.0;
        for (int completed = 0; completed < count; ++completed) {
            const double time_price = throughput_weight_ * count +
                                      latency_weight_ * suffix_weight[completed];
            for (int size = 1; completed + size <= count; ++size) {
                const double service =
                    schedule_cost_ + duration(DurationColumn::DECODE_POST, size);
                const double candidate = best[completed] + time_price * service;
                const int candidate_first = completed == 0 ? size : first[completed];
                const int next = completed + size;
                if (candidate + 1e-12 < best[next] ||
                    (abs(candidate - best[next]) <= 1e-12 &&
                     candidate_first > first[next])) {
                    best[next] = candidate;
                    first[next] = candidate_first;
                }
            }
        }
        return first[count];
    }
    // SUBMISSION_FEATURE_END exact_dpost_partition

    // SUBMISSION_FEATURE_BEGIN terminal_dpost
    vector<int> terminal_dpost_members() {
        vector<int> ready = collect_ready(d_post_ready_, RequestState::READY_D_POST);
        if (ready.empty()) {
            fail("terminal D POST selection found no ready members");
        }
        stable_sort(ready.begin(), ready.end(), [&](int left, int right) {
            const double left_value = decode_member_value(request(left), TaskKind::D_POST);
            const double right_value = decode_member_value(request(right), TaskKind::D_POST);
            if (abs(left_value - right_value) > 1e-12) {
                return left_value > right_value;
            }
            return request(left).ready_sequence < request(right).ready_sequence;
        });

        const int available = static_cast<int>(ready.size());
        const int fallback_size = best_group_size(
            DurationColumn::DECODE_POST, available
        );
        // SUBMISSION_FEATURE_BEGIN exact_dpost_partition
        const int partition_size = EXACT_DPOST_PARTITION
            ? exact_dpost_partition_first(ready)
            : fallback_size;
        // SUBMISSION_FEATURE_END exact_dpost_partition
        auto prefix = [&](int size) {
            return vector<int>(ready.begin(), ready.begin() + size);
        };
        if (available <= 1 || available > 96 || fallback_size <= 1 ||
            latency_weight_ <= 0.1 || distance_baseline_ <= 0) {
            return prefix(fallback_size);
        }

        set<int> sizes = {1, fallback_size, available};
        // SUBMISSION_FEATURE_BEGIN exact_dpost_partition
        sizes.insert(partition_size);
        // SUBMISSION_FEATURE_END exact_dpost_partition
        for (int size : {
                 fallback_size - 1,
                 fallback_size + 1,
                 fallback_size / 2,
                 min(available, 2 * fallback_size),
                 available / 4,
                 available / 2,
                 3 * available / 4,
             }) {
            if (1 <= size && size <= available) {
                sizes.insert(size);
            }
        }
        const vector<pair<int, double>>& curve =
            duration_curves_[static_cast<int>(DurationColumn::DECODE_POST)];
        for (int anchor : {fallback_size, available / 2}) {
            auto position = lower_bound(
                curve.begin(), curve.end(),
                make_pair(anchor, -numeric_limits<double>::infinity())
            );
            for (int offset = -2; offset <= 2; ++offset) {
                const long long index = distance(curve.begin(), position) + offset;
                if (0 <= index && index < static_cast<long long>(curve.size())) {
                    sizes.insert(min(available, curve[index].first));
                }
            }
        }

        vector<pair<double, int>> future_arrivals;
        int future_members = 0;
        for (const TransferPrediction& transfer : predicted_down_queue_) {
            if (!transfer.decode || transfer.finish_time < current_time_ - 1e-12 ||
                future_arrivals.size() >= 8 || future_members >= 96 - available) {
                continue;
            }
            const int members = min<int>(
                max<long long>(1, transfer.size_bytes / max<long long>(1, bytes_per_token_)),
                96 - available - future_members
            );
            if (members > 0) {
                future_arrivals.push_back({transfer.finish_time, members});
                future_members += members;
            }
        }

        auto value = [&](int first_size) {
            int completed_ready = 0;
            int queued = available;
            size_t arrival_index = 0;
            bool first_group = true;
            double virtual_time = current_time_;
            double gap_sum = observed_tpot_sum_;
            long long gap_count = observed_tpot_count_;
            while (queued > 0 || arrival_index < future_arrivals.size()) {
                if (queued == 0) {
                    virtual_time = max(
                        virtual_time, future_arrivals[arrival_index].first
                    );
                    while (arrival_index < future_arrivals.size() &&
                           future_arrivals[arrival_index].first <= virtual_time + 1e-12) {
                        queued += future_arrivals[arrival_index].second;
                        ++arrival_index;
                    }
                }
                const int group_size = first_group
                    ? first_size
                    : best_group_size(DurationColumn::DECODE_POST, queued);
                virtual_time += schedule_cost_ +
                                duration(DurationColumn::DECODE_POST, group_size);
                const int ready_end = min(
                    available, completed_ready + group_size
                );
                for (int index = completed_ready; index < ready_end; ++index) {
                    const Request& req = request(ready[index]);
                    if (req.produced_tokens > 0) {
                        gap_sum += virtual_time - req.decode_clock_start;
                        ++gap_count;
                    }
                }
                completed_ready = ready_end;
                queued -= group_size;
                while (arrival_index < future_arrivals.size() &&
                       future_arrivals[arrival_index].first <= virtual_time + 1e-12) {
                    queued += future_arrivals[arrival_index].second;
                    ++arrival_index;
                }
                first_group = false;
            }

            const double elapsed = virtual_time - current_time_;
            const double queue_rate =
                (available + future_members) / max(1e-12, elapsed);
            double throughput_component = 0;
            if (throughput_upper_bound_ > throughput_baseline_ + 1e-12) {
                throughput_component = max(
                    0.0,
                    min(
                        1.0,
                        (queue_rate - throughput_baseline_) /
                            (throughput_upper_bound_ - throughput_baseline_)
                    )
                );
            }
            const double mean_tdr = observed_tdr_count_ > 0
                ? observed_tdr_sum_ / observed_tdr_count_
                : 0;
            const double mean_tpot = gap_count > 0 ? gap_sum / gap_count : 0;
            const double excess_tdr = max(
                0.0, (mean_tdr - slo_tdr_) / max(1e-12, slo_tdr_)
            );
            const double excess_tpot = max(
                0.0, (mean_tpot - slo_tpot_) / max(1e-12, slo_tpot_)
            );
            const double score_distance = hypot(excess_tdr, excess_tpot);
            const double waiting_component = max(
                0.0, 1.0 - score_distance / distance_baseline_
            );
            return make_pair(
                1000.0 * (
                    throughput_weight_ * throughput_component +
                    latency_weight_ * waiting_component
                ),
                elapsed
            );
        };

        int best_size = fallback_size;
        const auto [fallback_value, fallback_clearance] = value(fallback_size);
        double best_value = fallback_value;
        const bool allow_relaxed_threshold =
            latency_weight_ <= DPOST_RELAXED_MAX_LATENCY_WEIGHT + 1e-12;
        const double clearance_ratio =
            allow_relaxed_threshold ? DPOST_CLEARANCE_RATIO : 0.98;
        const double score_margin = allow_relaxed_threshold ? DPOST_SCORE_MARGIN : 0.5;
        for (int size : sizes) {
            if (size < fallback_size
                // SUBMISSION_FEATURE_BEGIN exact_dpost_partition
                && (!EXACT_DPOST_PARTITION || size != partition_size)
                // SUBMISSION_FEATURE_END exact_dpost_partition
            ) {
                continue;
            }
            const auto [candidate_value, candidate_clearance] = value(size);
            if (candidate_clearance <= clearance_ratio * fallback_clearance + 1e-12 &&
                candidate_value > best_value + score_margin) {
                best_value = candidate_value;
                best_size = size;
            }
        }
        if (best_value < fallback_value + score_margin) {
            return prefix(fallback_size);
        }
        return prefix(best_size);
    }
    // SUBMISSION_FEATURE_END terminal_dpost

    // SUBMISSION_FEATURE_BEGIN terminal_dproc
    vector<int> terminal_dproc_members(int cloud) {
        vector<int> ready = collect_ready(
            d_proc_ready_[cloud], RequestState::READY_D_PROC
        );
        if (ready.empty()) {
            fail("terminal D PROC selection found no ready members");
        }
        stable_sort(ready.begin(), ready.end(), [&](int left, int right) {
            const double left_value = decode_member_value(request(left), TaskKind::D_PROC);
            const double right_value = decode_member_value(request(right), TaskKind::D_PROC);
            if (abs(left_value - right_value) > 1e-12) {
                return left_value > right_value;
            }
            return request(left).ready_sequence < request(right).ready_sequence;
        });

        const int available = static_cast<int>(ready.size());
        const int fallback_size = best_group_size(
            DurationColumn::DECODE_PROC, available
        );
        auto prefix = [&](int size) {
            return vector<int>(ready.begin(), ready.begin() + size);
        };
        if (available <= 1 || available > 96 || cloud_count_ != 1 ||
            throughput_weight_ < 0.95 ||
            (latency_weight_ > 0 && distance_baseline_ <= 0)) {
            return prefix(fallback_size);
        }

        set<int> sizes = {fallback_size, available};
        for (int size : {
                 fallback_size - 1,
                 fallback_size + 1,
                 2 * fallback_size,
                 available / 4,
                 available / 2,
                 3 * available / 4,
             }) {
            if (fallback_size <= size && size <= available) {
                sizes.insert(size);
            }
        }
        const vector<pair<int, double>>& proc_curve =
            duration_curves_[static_cast<int>(DurationColumn::DECODE_PROC)];
        for (int anchor : {fallback_size, available / 2}) {
            auto position = lower_bound(
                proc_curve.begin(), proc_curve.end(),
                make_pair(anchor, -numeric_limits<double>::infinity())
            );
            for (int offset = -2; offset <= 2; ++offset) {
                const long long index = distance(proc_curve.begin(), position) + offset;
                if (0 <= index && index < static_cast<long long>(proc_curve.size())) {
                    const int candidate = min(available, proc_curve[index].first);
                    if (candidate >= fallback_size) {
                        sizes.insert(candidate);
                    }
                }
            }
        }

        vector<pair<double, int>> future_up;
        int future_up_members = 0;
        for (const TransferPrediction& transfer : predicted_up_queue_) {
            if (!transfer.decode || transfer.remote != cloud ||
                transfer.finish_time < current_time_ - 1e-12 ||
                future_up.size() >= 8 || future_up_members >= 96 - available) {
                continue;
            }
            const int members = min<int>(
                max<long long>(1, transfer.size_bytes / max<long long>(1, bytes_per_token_)),
                96 - available - future_up_members
            );
            if (members > 0) {
                future_up.push_back({transfer.finish_time, members});
                future_up_members += members;
            }
        }

        struct Arrival {
            double time;
            vector<int> items;
        };
        struct PendingDown {
            double proc_finish;
            vector<int> items;
        };
        auto value = [&](int first_size) {
            vector<Arrival> post_arrivals;
            if (!d_post_ready_.empty()) {
                post_arrivals.push_back(
                    {current_time_, vector<int>(d_post_ready_.size(), -1)}
                );
            }
            int modeled_post_members = static_cast<int>(d_post_ready_.size());
            for (const TransferPrediction& transfer : predicted_down_queue_) {
                if (!transfer.decode || transfer.finish_time < current_time_ - 1e-12 ||
                    post_arrivals.size() >= 12 || modeled_post_members >= 192) {
                    continue;
                }
                const int members = min<int>(
                    max<long long>(1, transfer.size_bytes / max<long long>(1, bytes_per_token_)),
                    192 - modeled_post_members
                );
                if (members > 0) {
                    post_arrivals.push_back(
                        {transfer.finish_time, vector<int>(members, -1)}
                    );
                    modeled_post_members += members;
                }
            }

            vector<PendingDown> generated_down;
            double proc_time = current_time_;
            int queued = available;
            int tagged_index = 0;
            size_t up_index = 0;
            bool first_group = true;
            while (queued > 0 || up_index < future_up.size()) {
                if (queued == 0) {
                    proc_time = max(proc_time, future_up[up_index].first);
                    while (up_index < future_up.size() &&
                           future_up[up_index].first <= proc_time + 1e-12) {
                        queued += future_up[up_index].second;
                        ++up_index;
                    }
                }
                const int group_size = first_group
                    ? first_size
                    : best_group_size(DurationColumn::DECODE_PROC, queued);
                vector<int> items;
                items.reserve(group_size);
                for (int index = 0; index < group_size; ++index) {
                    if (tagged_index < available) {
                        items.push_back(tagged_index++);
                    } else {
                        items.push_back(-1);
                    }
                }
                proc_time += schedule_cost_ +
                             duration(DurationColumn::DECODE_PROC, group_size);
                generated_down.push_back({proc_time, std::move(items)});
                modeled_post_members += group_size;
                queued -= group_size;
                while (up_index < future_up.size() &&
                       future_up[up_index].first <= proc_time + 1e-12) {
                    queued += future_up[up_index].second;
                    ++up_index;
                }
                first_group = false;
            }

            for (int other = 0; other < cloud_count_; ++other) {
                if (other == cloud) {
                    continue;
                }
                int group_size = 0;
                double finish = current_time_;
                if (cloud_busy_[other] &&
                    cloud_running_kind_[other] == TaskKind::D_PROC &&
                    cloud_running_group_size_[other] > 0) {
                    group_size = cloud_running_group_size_[other];
                    finish = cloud_busy_until_[other];
                } else if (!cloud_busy_[other] && p_proc_ready_[other].empty() &&
                           !d_proc_ready_[other].empty()) {
                    group_size = best_group_size(
                        DurationColumn::DECODE_PROC,
                        static_cast<int>(d_proc_ready_[other].size())
                    );
                    finish += schedule_cost_ +
                              duration(DurationColumn::DECODE_PROC, group_size);
                }
                if (group_size > 0) {
                    generated_down.push_back(
                        {finish, vector<int>(group_size, -1)}
                    );
                    modeled_post_members += group_size;
                }
            }
            stable_sort(
                generated_down.begin(), generated_down.end(),
                [](const PendingDown& left, const PendingDown& right) {
                    return left.proc_finish < right.proc_finish;
                }
            );
            double down_tail = max(current_time_, predicted_down_tail_);
            for (PendingDown& pending : generated_down) {
                down_tail = max(down_tail, pending.proc_finish) + transfer_time(
                    static_cast<long long>(pending.items.size()) * bytes_per_token_
                );
                post_arrivals.push_back({down_tail, std::move(pending.items)});
            }

            stable_sort(
                post_arrivals.begin(), post_arrivals.end(),
                [](const Arrival& left, const Arrival& right) {
                    return left.time < right.time;
                }
            );
            deque<int> post_queue;
            size_t arrival_index = 0;
            double edge_time = edge_busy_ ? edge_busy_until_ : current_time_;
            double gap_sum = observed_tpot_sum_;
            long long gap_count = observed_tpot_count_;
            while (!post_queue.empty() || arrival_index < post_arrivals.size()) {
                if (post_queue.empty()) {
                    edge_time = max(edge_time, post_arrivals[arrival_index].time);
                }
                while (arrival_index < post_arrivals.size() &&
                       post_arrivals[arrival_index].time <= edge_time + 1e-12) {
                    post_queue.insert(
                        post_queue.end(),
                        post_arrivals[arrival_index].items.begin(),
                        post_arrivals[arrival_index].items.end()
                    );
                    ++arrival_index;
                }
                if (post_queue.empty()) {
                    continue;
                }
                const int group_size = best_group_size(
                    DurationColumn::DECODE_POST,
                    static_cast<int>(post_queue.size())
                );
                edge_time += schedule_cost_ +
                             duration(DurationColumn::DECODE_POST, group_size);
                for (int index = 0; index < group_size; ++index) {
                    const int tagged = post_queue.front();
                    post_queue.pop_front();
                    if (tagged >= 0) {
                        const Request& req = request(ready[tagged]);
                        if (req.produced_tokens > 0) {
                            gap_sum += edge_time - req.decode_clock_start;
                            ++gap_count;
                        }
                    }
                }
            }

            const double clearance = edge_time - current_time_;
            const double queue_rate = modeled_post_members / max(1e-12, clearance);
            double throughput_component = 0;
            if (throughput_upper_bound_ > throughput_baseline_ + 1e-12) {
                throughput_component = max(
                    0.0,
                    min(
                        1.0,
                        (queue_rate - throughput_baseline_) /
                            (throughput_upper_bound_ - throughput_baseline_)
                    )
                );
            }
            const double mean_tdr = observed_tdr_count_ > 0
                ? observed_tdr_sum_ / observed_tdr_count_
                : 0;
            const double mean_tpot = gap_count > 0 ? gap_sum / gap_count : 0;
            const double excess_tdr = max(
                0.0, (mean_tdr - slo_tdr_) / max(1e-12, slo_tdr_)
            );
            const double excess_tpot = max(
                0.0, (mean_tpot - slo_tpot_) / max(1e-12, slo_tpot_)
            );
            const double score_distance = hypot(excess_tdr, excess_tpot);
            const double waiting_component = distance_baseline_ > 0
                ? max(0.0, 1.0 - score_distance / distance_baseline_)
                : (score_distance == 0 ? 1.0 : 0.0);
            return make_pair(
                1000.0 * (
                    throughput_weight_ * throughput_component +
                    latency_weight_ * waiting_component
                ),
                clearance
            );
        };

        int best_size = fallback_size;
        const auto [fallback_value, fallback_clearance] = value(fallback_size);
        double best_value = fallback_value;
        const double fallback_proc_per_member =
            (schedule_cost_ + duration(DurationColumn::DECODE_PROC, fallback_size)) /
            fallback_size;
        for (int size : sizes) {
            const double candidate_proc_per_member =
                (schedule_cost_ + duration(DurationColumn::DECODE_PROC, size)) / size;
            if (candidate_proc_per_member >
                    1.075 * fallback_proc_per_member + 1e-12 ||
                downstream_group_is_hostile(size)) {
                continue;
            }
            const auto [candidate_value, candidate_clearance] = value(size);
            if (candidate_clearance <= DPROC_CLEARANCE_RATIO * fallback_clearance + 1e-12 &&
                candidate_value > best_value + DPROC_SCORE_MARGIN) {
                best_value = candidate_value;
                best_size = size;
            }
        }
        if (best_value < fallback_value + DPROC_SCORE_MARGIN) {
            return prefix(fallback_size);
        }
        return prefix(best_size);
    }
    // SUBMISSION_FEATURE_END terminal_dproc


    vector<int> legacy_d_pre_members() {
        vector<int> ready = collect_ready(d_pre_ready_, RequestState::READY_D_PRE);
        if (ready.empty()) {
            fail("D PRE group selection found no ready members");
        }
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 9) {
            const int size = best_group_size(DurationColumn::DECODE_PRE, ready.size());
            ready.resize(size);
            return ready;
        }
        // SUBMISSION_FEATURE_END pre20_only
        if (latency_weight_ > throughput_weight_) {
            const int size = best_group_size(DurationColumn::DECODE_PRE, ready.size());
            ready.resize(size);
            return ready;
        }

        map<int, vector<int>> by_cloud;
        for (int request_id : ready) {
            by_cloud[request(request_id).cloud].push_back(request_id);
        }

        vector<vector<int>> groups;
        for (int size : candidate_group_sizes(ready.size())) {
            groups.emplace_back(ready.begin(), ready.begin() + size);
            for (const auto& [anchor_cloud, anchor_members] : by_cloud) {
                vector<int> packed;
                packed.reserve(size);
                for (int request_id : anchor_members) {
                    if (static_cast<int>(packed.size()) == size) {
                        break;
                    }
                    packed.push_back(request_id);
                }
                vector<pair<int, int>> other_clouds;
                for (const auto& [cloud, members] : by_cloud) {
                    if (cloud != anchor_cloud) {
                        other_clouds.push_back({-static_cast<int>(members.size()), cloud});
                    }
                }
                sort(other_clouds.begin(), other_clouds.end());
                for (const auto& [ignored_count, cloud] : other_clouds) {
                    (void)ignored_count;
                    for (int request_id : by_cloud[cloud]) {
                        if (static_cast<int>(packed.size()) == size) {
                            break;
                        }
                        packed.push_back(request_id);
                    }
                    if (static_cast<int>(packed.size()) == size) {
                        break;
                    }
                }
                if (static_cast<int>(packed.size()) == size) {
                    groups.push_back(std::move(packed));
                }
            }
        }

        vector<int> best_group = {ready.front()};
        double best_value = -numeric_limits<double>::infinity();
        int best_fanout = numeric_limits<int>::max();
        set<vector<int>> seen;
        for (vector<int> group : groups) {
            vector<int> identity = group;
            sort(identity.begin(), identity.end());
            if (!seen.insert(identity).second) {
                continue;
            }
            vector<int> counts(cloud_count_, 0);
            double urgency_sum = 0;
            for (int request_id : group) {
                ++counts[request(request_id).cloud];
                urgency_sum += request_urgency(TaskKind::D_PRE, request(request_id));
            }

            const double edge_finish = current_time_ + schedule_cost_ +
                                       duration(DurationColumn::DECODE_PRE, group.size());
            double up_tail = max(edge_finish, predicted_up_tail_);
            vector<double> cloud_up_finish(cloud_count_, 0);
            int fanout = 0;
            for (int cloud = 0; cloud < cloud_count_; ++cloud) {
                if (counts[cloud] == 0) {
                    continue;
                }
                ++fanout;
                up_tail += transfer_time(
                    static_cast<long long>(counts[cloud]) * bytes_per_token_
                );
                cloud_up_finish[cloud] = up_tail;
            }

            double milestone_finish = up_tail;
            if constexpr (kOptimizationLevel >= 15) {
                if (!downstream_group_is_hostile(group.size())) {
                    const double horizon = max(1e-9, milestone_finish - current_time_);
                    const double rate = group.size() / horizon;
                    const double mean_urgency = urgency_sum / group.size();
                    const double value = throughput_weight_ * rate +
                                         latency_weight_ * mean_urgency / horizon -
                                         0.001 * fanout;
                    if (value > best_value + 1e-12 ||
                        (abs(value - best_value) <= 1e-12 && fanout < best_fanout)) {
                        best_value = value;
                        best_fanout = fanout;
                        best_group = std::move(group);
                    }
                    continue;
                }
                double down_tail = max(current_time_, predicted_down_tail_);
                for (int cloud = 0; cloud < cloud_count_; ++cloud) {
                    if (counts[cloud] == 0) {
                        continue;
                    }
                    const double proc_finish =
                        max(cloud_up_finish[cloud], cloud_busy_until_[cloud]) + schedule_cost_ +
                        duration(DurationColumn::DECODE_PROC, counts[cloud]);
                    down_tail = max(down_tail, proc_finish) + transfer_time(
                        static_cast<long long>(counts[cloud]) * bytes_per_token_
                    );
                }
                milestone_finish = down_tail + schedule_cost_ +
                                   duration(DurationColumn::DECODE_POST, group.size());
            }
            const double horizon = max(1e-9, milestone_finish - current_time_);
            const double rate = group.size() / horizon;
            const double mean_urgency = urgency_sum / group.size();
            const double value = throughput_weight_ * rate +
                                 latency_weight_ * mean_urgency / horizon -
                                 0.001 * fanout;
            if (value > best_value + 1e-12 ||
                (abs(value - best_value) <= 1e-12 && fanout < best_fanout)) {
                best_value = value;
                best_fanout = fanout;
                best_group = std::move(group);
            }
        }
        return best_group;
    }

    vector<int> legacy_decode_members(
        deque<int>& queue,
        RequestState expected,
        TaskKind kind,
        DurationColumn column
    ) {
        vector<int> ready = collect_ready(queue, expected);
        const int group_size = best_group_size(column, ready.size());
        stable_sort(ready.begin(), ready.end(), [&](int left, int right) {
            const double left_value = decode_member_value(request(left), kind);
            const double right_value = decode_member_value(request(right), kind);
            if (abs(left_value - right_value) > 1e-12) {
                return left_value > right_value;
            }
            return request(left).ready_sequence < request(right).ready_sequence;
        });
        ready.resize(group_size);
        return ready;
    }

    vector<int> choose_d_pre_members() {
                // SUBMISSION_FEATURE_BEGIN experimental_grouping
        if constexpr (kExperimentalGrouping) {
            const vector<int> fallback = legacy_d_pre_members();
            return choose_counterfactual_decode_group(
                d_pre_ready_,
                RequestState::READY_D_PRE,
                TaskKind::D_PRE,
                DurationColumn::DECODE_PRE,
                true,
                fallback
            );
        }
        // SUBMISSION_FEATURE_END experimental_grouping
        return legacy_d_pre_members();
    }

    bool should_wait_for_group(
        TaskKind kind,
        DurationColumn column,
        int cloud,
        int available,
        double oldest_ready_time,
        bool allow_wait
    ) const {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 5) {
            return false;
        }
        // SUBMISSION_FEATURE_END pre20_only
        // SUBMISSION_FEATURE_BEGIN cohort_dpost
        if constexpr (COHORT_DPOST_WAIT && kOptimizationLevel >= 20) {
            if (kind == TaskKind::D_POST) {
                if (!allow_wait || throughput_weight_ < 0.8 || available < 4) {
                    return false;
                }
                const int possible = max(total_active_decode_requests_, available);
                const int target = best_group_size(column, possible);
                if (available >= target) {
                    return false;
                }
                int future_members = 0;
                double wake_time = numeric_limits<double>::infinity();
                auto consider_future = [&](double finish_time, int members) {
                    if (finish_time + 1e-12 < wake_time) {
                        wake_time = finish_time;
                        future_members = members;
                    } else if (abs(finish_time - wake_time) <= 1e-12) {
                        future_members += members;
                    }
                };
                for (const TransferPrediction& transfer : predicted_down_queue_) {
                    if (!transfer.decode || transfer.finish_time < current_time_ - 1e-12) {
                        continue;
                    }
                    consider_future(
                        transfer.finish_time,
                        static_cast<int>(max<long long>(
                            1, transfer.size_bytes / max<long long>(1, bytes_per_token_)
                        ))
                    );
                }
                for (int future_cloud = 0; future_cloud < cloud_count_; ++future_cloud) {
                    if (!cloud_busy_[future_cloud] ||
                        cloud_running_kind_[future_cloud] != TaskKind::D_PROC ||
                        cloud_busy_until_[future_cloud] < current_time_ - 1e-12) {
                        continue;
                    }
                    const int members = max(1, cloud_running_group_size_[future_cloud]);
                    consider_future(
                        cloud_busy_until_[future_cloud] + transfer_time(
                            static_cast<long long>(members) * bytes_per_token_
                        ),
                        members
                    );
                }
                if (future_members <= 0 || !isfinite(wake_time)) {
                    return false;
                }
                double previous_duration = duration(column, 1);
                double previous_rate = 1.0 / (schedule_cost_ + previous_duration);
                for (int size = 2; size <= possible; ++size) {
                    const double next_duration = duration(column, size);
                    const double rate = static_cast<double>(size) /
                        (schedule_cost_ + next_duration);
                    if (next_duration + 1e-12 < previous_duration ||
                        rate + 1e-12 < previous_rate) {
                        return false;
                    }
                    previous_duration = next_duration;
                    previous_rate = rate;
                }
                const int merged_size = best_group_size(
                    column, min(possible, available + future_members)
                );
                if (merged_size <= available) {
                    return false;
                }
                const int remainder = merged_size - available;
                const double split_cost =
                    2.0 * schedule_cost_ + duration(column, available) +
                    duration(column, remainder);
                const double merged_cost = schedule_cost_ + duration(column, merged_size);
                return wake_time - current_time_ <=
                       COHORT_DPOST_MAX_WAIT_FRACTION *
                           max(0.0, split_cost - merged_cost) + 1e-12;
            }
        }
        // SUBMISSION_FEATURE_END cohort_dpost
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
        const double wait_urgency =
            kOptimizationLevel >= 11 && latency_weight_ <= throughput_weight_
                ? observed_request_urgency(kind, oldest)
                : request_urgency(kind, oldest);
        if (wait_urgency >= 0.5) {
            return false;
        }
        const double wait_budget = slo_tpot_ * (0.02 + 0.18 * throughput_weight_);
        const double waited = current_time_ - oldest_ready_time;
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 8) {
            return waited + 1e-12 < wait_budget && has_known_future_event();
        }
        // SUBMISSION_FEATURE_END pre20_only
        if (throughput_weight_ > 0.995) {
            return waited + 1e-12 < wait_budget && has_known_future_event();
        }
        double wake_time = next_known_event_time();
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 9) {
        // SUBMISSION_FEATURE_END pre20_only
            wake_time = next_compatible_event_time(kind, cloud);
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        if (!isfinite(wake_time)) {
            return false;
        }
        const double remaining_budget = wait_budget - waited;
        return remaining_budget > 1e-12 &&
               wake_time - current_time_ <= remaining_budget + 1e-12;
    }

    bool should_defer_prefill_admission(const Request& req, bool allow_wait) const {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 7) {
            return false;
        }
        // SUBMISSION_FEATURE_END pre20_only
        // SUBMISSION_FEATURE_BEGIN link_admission_fairness
        if constexpr (LINK_ADMISSION_FAIRNESS) {
            bool progress_source = has_known_future_event();
            for (const deque<int>& queue : p_proc_ready_) {
                progress_source = progress_source || !queue.empty();
            }
            for (const deque<int>& queue : d_proc_ready_) {
                progress_source = progress_source || !queue.empty();
            }
            progress_source = progress_source || !p_post_ready_.empty() ||
                              !d_pre_ready_.empty() || !d_post_ready_.empty();
            const double request_transfer = transfer_time(
                static_cast<long long>(req.input_length) * bytes_per_token_
            );
            const bool earlier_pipeline = any_of(
                active_requests_.begin(), active_requests_.end(),
                [](int active) { return active > 0; }
            );
            if (progress_source && throughput_weight_ >= 0.5 &&
                request_transfer > 4.0 * slo_tpot_) {
                if (total_active_decode_requests_ > 0 || !d_pre_ready_.empty() ||
                    (total_active_decode_requests_ == 0 && earlier_pipeline &&
                     current_time_ - req.arrival_time < 0.1 * slo_tdr_)) {
                    return true;
                }
            }
        }
        // SUBMISSION_FEATURE_END link_admission_fairness
        if (!allow_wait) {
            return false;
        }
        if (!has_known_future_event()) {
            return false;
        }
        if (pending_up_transfers_ == 0) {
            return false;
        }
        const double pressure = kOptimizationLevel >= 8
            ? predicted_link_delay("UP")
            : transfer_time(pending_up_bytes_, pending_up_transfers_);
        const double age = current_time_ - req.arrival_time;
        // SUBMISSION_FEATURE_BEGIN link_admission_fairness
        if constexpr (LINK_ADMISSION_FAIRNESS) {
            const double request_transfer = transfer_time(
                static_cast<long long>(req.input_length) * bytes_per_token_
            );
            if (throughput_weight_ >= 0.5 && request_transfer > 4.0 * slo_tpot_) {
                if (pressure > slo_tpot_ && pending_up_bytes_ > bytes_per_token_ &&
                    (age < 0.05 * slo_tdr_ || !d_pre_ready_.empty())) {
                    return true;
                }
            }
        }
        // SUBMISSION_FEATURE_END link_admission_fairness
        if (latency_weight_ < 0.8) {
            return false;
        }
        // Never hold admission for a large fraction of SLO1: without a timer, one deferral can
        // last until a much later transfer. This narrow guard only avoids adding another large
        // prefill behind an already extreme UP backlog.
        double threshold = slo_tdr_;
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 14) {
        // SUBMISSION_FEATURE_END pre20_only
            threshold = min(slo_tdr_, 0.5 * max(slo_tdr_, slo_tpot_));
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        return pressure > threshold && age < 0.05 * slo_tdr_;
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
                const int cloud = choose_cloud(req);
                req.cloud = cloud;
                req.state = RequestState::RUNNING_P_PRE;
                ++active_requests_[cloud];
                pending_prefill_work_[cloud] += duration(DurationColumn::PREFILL_PROC, req.input_length);
                edge_busy_ = true;
                edge_running_kind_ = TaskKind::P_PRE;
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
                edge_running_kind_ = TaskKind::P_POST;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::PREFILL_POST, req.input_length);
                return "E P POST " + to_string(req.cloud) + " " + to_string(request_id);
            }

            if (candidate.kind == TaskKind::D_PRE) {
                // SUBMISSION_FEATURE_BEGIN initial_decode_barrier
                if constexpr (INITIAL_DECODE_BARRIER) {
                    if (allow_wait && should_hold_initial_decode_frontier()) {
                        continue;
                    }
                }
                // SUBMISSION_FEATURE_END initial_decode_barrier
                // SUBMISSION_FEATURE_BEGIN prefill_cohort_wait
                if constexpr (PREFILL_COHORT_WAIT) {
                    if (allow_wait && should_wait_for_prefill_cohort()) {
                        continue;
                    }
                }
                // SUBMISSION_FEATURE_END prefill_cohort_wait
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
                vector<int> selected = choose_d_pre_members();
                vector<int> members = take_selected(
                    d_pre_ready_, RequestState::READY_D_PRE, selected
                );
                // SUBMISSION_FEATURE_BEGIN pre20_only
                if constexpr (COHERENT_DECODE_BATCH && kOptimizationLevel >= 20) {
                // SUBMISSION_FEATURE_END pre20_only
                    if (coherent_decode_enabled()) {
                        coherent_decode_batch_ = members;
                    }
                // SUBMISSION_FEATURE_BEGIN pre20_only
                }
                // SUBMISSION_FEATURE_END pre20_only
                // SUBMISSION_FEATURE_BEGIN dynamic_coherent_dpost
                if constexpr (DYNAMIC_COHERENT_DPOST) {
                    if (dynamic_coherent_dpost_enabled(members)) {
                        coherent_decode_batch_ = members;
                    }
                }
                // SUBMISSION_FEATURE_END dynamic_coherent_dpost
                for (int request_id : members) {
                    request(request_id).state = RequestState::RUNNING_D_PRE;
                }
                edge_busy_ = true;
                edge_running_kind_ = TaskKind::D_PRE;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::DECODE_PRE, members.size());
                return "E D PRE -1 " + to_string(members.size()) + join_members(members);
            }

            if (candidate.kind == TaskKind::D_POST) {
                // SUBMISSION_FEATURE_BEGIN cohort_dpost
                if constexpr (COHORT_DPOST_WAIT && kOptimizationLevel >= 20) {
                    const int available = static_cast<int>(d_post_ready_.size());
                    const int oldest = queue_front(
                        d_post_ready_, RequestState::READY_D_POST
                    );
                    if (should_wait_for_group(
                            TaskKind::D_POST,
                            DurationColumn::DECODE_POST,
                            -1,
                            available,
                            request(oldest).ready_time,
                            allow_wait
                        )) {
                        continue;
                    }
                }
                // SUBMISSION_FEATURE_END cohort_dpost
                vector<int> members;
                // SUBMISSION_FEATURE_BEGIN pre20_only
                if constexpr (COHERENT_DECODE_BATCH && kOptimizationLevel >= 20) {
                // SUBMISSION_FEATURE_END pre20_only
                    if (!coherent_decode_batch_.empty()) {
                        bool cohort_ready = !coherent_decode_batch_.empty();
                        for (int request_id : coherent_decode_batch_) {
                            if (request(request_id).state != RequestState::READY_D_POST) {
                                cohort_ready = false;
                                break;
                            }
                        }
                        if (!cohort_ready) {
                            continue;
                        }
                        members = take_selected(
                            d_post_ready_, RequestState::READY_D_POST, coherent_decode_batch_
                        );
                        coherent_decode_batch_.clear();
                    }
                // SUBMISSION_FEATURE_BEGIN pre20_only
                }
                // SUBMISSION_FEATURE_END pre20_only
                // SUBMISSION_FEATURE_BEGIN terminal_dpost
                if (members.empty()) {
                    if constexpr (kTerminalDPostOptimizer) {
                        vector<int> selected = terminal_dpost_members();
                        members = take_selected(
                            d_post_ready_, RequestState::READY_D_POST, selected
                        );
                    }
                }
                // SUBMISSION_FEATURE_END terminal_dpost
                // SUBMISSION_FEATURE_BEGIN experimental_grouping
                if (members.empty()) {
                    if constexpr (kExperimentalGrouping) {
                        const vector<int> fallback = legacy_decode_members(
                            d_post_ready_,
                            RequestState::READY_D_POST,
                            TaskKind::D_POST,
                            DurationColumn::DECODE_POST
                        );
                        vector<int> selected = choose_counterfactual_decode_group(
                            d_post_ready_,
                            RequestState::READY_D_POST,
                            TaskKind::D_POST,
                            DurationColumn::DECODE_POST,
                            false,
                            fallback
                        );
                        members = take_selected(
                            d_post_ready_, RequestState::READY_D_POST, selected
                        );
                    }
                }
                // SUBMISSION_FEATURE_END experimental_grouping
                if (members.empty()) {
                    const int available = static_cast<int>(d_post_ready_.size());
                    const int group_size = best_group_size(
                        DurationColumn::DECODE_POST, available
                    );
                    members = take_decode_members(
                        d_post_ready_,
                        RequestState::READY_D_POST,
                        group_size,
                        TaskKind::D_POST
                    );
                }
                const int group_size = static_cast<int>(members.size());
                for (int request_id : members) {
                    request(request_id).state = RequestState::RUNNING_D_POST;
                }
                edge_busy_ = true;
                edge_running_kind_ = TaskKind::D_POST;
                edge_busy_until_ = current_time_ + schedule_cost_ +
                                   duration(DurationColumn::DECODE_POST, group_size);
                return "E D POST -1 " + to_string(group_size) + join_members(members);
            }
        }
        return nullopt;
    }

    int choose_prefill_piece_end(const Request& req, int cloud) const {
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel < 6) {
            return layer_count_;
        }
        // SUBMISSION_FEATURE_END pre20_only
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
        double target_duration = max(
            4.0 * schedule_cost_,
            min(0.25 * slo_tdr_, token_multiple * slo_tpot_)
        );
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 12) {
        // SUBMISSION_FEATURE_END pre20_only
            double next_decode_milestone = next_compatible_event_time(TaskKind::D_PROC, cloud);
            for (const Request& active : requests_) {
                if (active.state == RequestState::UNSEEN ||
                    active.state == RequestState::FINISHED || active.cloud != cloud ||
                    static_cast<int>(active.state) <
                        static_cast<int>(RequestState::READY_D_PRE)) {
                    continue;
                }
                next_decode_milestone = min(
                    next_decode_milestone,
                    active.decode_clock_start + slo_tpot_
                );
            }
            if (isfinite(next_decode_milestone)) {
                const double occupied_budget = max(
                    2.0 * schedule_cost_,
                    next_decode_milestone - current_time_
                );
                target_duration = min(target_duration, occupied_budget);
            }
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        double compute_budget = target_duration;
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 12) {
        // SUBMISSION_FEATURE_END pre20_only
            compute_budget = max(
                full_duration / layer_count_,
                target_duration - schedule_cost_
            );
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        const double raw_piece_layers =
            compute_budget * layer_count_ / max(1e-12, full_duration);
        int piece_layers = 1;
        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 12) {
        // SUBMISSION_FEATURE_END pre20_only
            piece_layers = static_cast<int>(floor(raw_piece_layers));
        // SUBMISSION_FEATURE_BEGIN pre20_only
        } else {
            piece_layers = static_cast<int>(ceil(raw_piece_layers));
        }
        // SUBMISSION_FEATURE_END pre20_only
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
            const int group_size = kind == TaskKind::D_PROC
                ? best_group_size(DurationColumn::DECODE_PROC, queue.size())
                : 1;
            candidates.push_back(
                {kind,
                 request_id,
                 req.ready_sequence,
                 request_urgency(kind, req),
                 rank,
                 action_value(kind, req, group_size)}
            );
        };
        add(TaskKind::P_PROC, p_proc_ready_[cloud], RequestState::READY_P_PROC, 1);
        add(TaskKind::D_PROC, d_proc_ready_[cloud], RequestState::READY_D_PROC, 0);

        // SUBMISSION_FEATURE_BEGIN pre20_only
        if constexpr (kOptimizationLevel >= 11) {
        // SUBMISSION_FEATURE_END pre20_only
            stable_sort(candidates.begin(), candidates.end(), [this](const Candidate& left, const Candidate& right) {
                return score_aware_candidate_less(left, right);
            });
        // SUBMISSION_FEATURE_BEGIN pre20_only
        }
        // SUBMISSION_FEATURE_END pre20_only
        // SUBMISSION_FEATURE_BEGIN legacy_priority
        else if constexpr (kOptimizationLevel < 5) {
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
        if constexpr (kOptimizationLevel >= 7 && kOptimizationLevel < 11) {
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
        // SUBMISSION_FEATURE_END legacy_priority
        // SUBMISSION_FEATURE_BEGIN objective_margin_rollout
        if constexpr (OBJECTIVE_MARGIN_ROLLOUT) {
            apply_objective_margin_rollout(candidates);
        }
        // SUBMISSION_FEATURE_END objective_margin_rollout
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
                // SUBMISSION_FEATURE_BEGIN prefill_cohort_wait
                if constexpr (PREFILL_COHORT_WAIT) {
                    req.running_prefill_layer_end = layer_end;
                }
                // SUBMISSION_FEATURE_END prefill_cohort_wait
                const double piece_duration =
                    duration(DurationColumn::PREFILL_PROC, req.input_length) *
                    (layer_end - layer_start) / static_cast<double>(layer_count_);
                pending_prefill_work_[cloud] = max(
                    0.0, pending_prefill_work_[cloud] - piece_duration
                );
                req.state = RequestState::RUNNING_P_PROC;
                cloud_busy_[cloud] = true;
                cloud_running_kind_[cloud] = TaskKind::P_PROC;
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
                vector<int> members;
                // SUBMISSION_FEATURE_BEGIN terminal_dproc
                if constexpr (kTerminalDProcOptimizer) {
                    vector<int> selected = terminal_dproc_members(cloud);
                    members = take_selected(
                        d_proc_ready_[cloud], RequestState::READY_D_PROC, selected
                    );
                } else
                // SUBMISSION_FEATURE_END terminal_dproc
                // SUBMISSION_FEATURE_BEGIN experimental_grouping
                if constexpr (kExperimentalGrouping) {
                    const vector<int> fallback = legacy_decode_members(
                        d_proc_ready_[cloud],
                        RequestState::READY_D_PROC,
                        TaskKind::D_PROC,
                        DurationColumn::DECODE_PROC
                    );
                    vector<int> selected = choose_counterfactual_decode_group(
                        d_proc_ready_[cloud],
                        RequestState::READY_D_PROC,
                        TaskKind::D_PROC,
                        DurationColumn::DECODE_PROC,
                        false,
                        fallback
                    );
                    members = take_selected(
                        d_proc_ready_[cloud], RequestState::READY_D_PROC, selected
                    );
                } else
                // SUBMISSION_FEATURE_END experimental_grouping
                {
                    const int selected_size = best_group_size(
                        DurationColumn::DECODE_PROC, available
                    );
                    members = take_decode_members(
                        d_proc_ready_[cloud],
                        RequestState::READY_D_PROC,
                        selected_size,
                        TaskKind::D_PROC
                    );
                }
                const int group_size = static_cast<int>(members.size());
                for (int request_id : members) {
                    request(request_id).state = RequestState::RUNNING_D_PROC;
                }
                cloud_busy_[cloud] = true;
                cloud_running_kind_[cloud] = TaskKind::D_PROC;
                // SUBMISSION_FEATURE_BEGIN terminal_dproc
                cloud_running_group_size_[cloud] = group_size;
                // SUBMISSION_FEATURE_END terminal_dproc
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
