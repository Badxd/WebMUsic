#include "roomstate.hpp"
#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>

namespace bot::net {
namespace {

i64 now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

std::mutex mu;
std::map<i64, std::string> titles;
std::map<i64, std::map<i64, std::pair<Person, i64>>> listeners;  // chat -> user_id -> (person, last_seen_ms)
std::map<i64, std::vector<ChatMsg>> chat_logs;

constexpr i64 kPresenceWindowMs = 30'000;

}  // namespace

void cache_chat_title(i64 chat_id, const std::string& title) {
    if (title.empty()) return;
    std::lock_guard<std::mutex> lk(mu);
    titles[chat_id] = title;
}

std::string get_chat_title(i64 chat_id) {
    std::lock_guard<std::mutex> lk(mu);
    auto it = titles.find(chat_id);
    return it != titles.end() ? it->second : "Room";
}

void touch_listener(i64 chat_id, const Person& p) {
    if (!p.user_id) return;
    std::lock_guard<std::mutex> lk(mu);
    listeners[chat_id][p.user_id] = {p, now_ms()};
}

std::vector<Person> get_listeners(i64 chat_id) {
    std::lock_guard<std::mutex> lk(mu);
    std::vector<Person> out;
    auto it = listeners.find(chat_id);
    if (it == listeners.end()) return out;
    i64 cutoff = now_ms() - kPresenceWindowMs;
    for (auto& [uid, pair] : it->second)
        if (pair.second >= cutoff) out.push_back(pair.first);
    return out;
}

int listener_count(i64 chat_id) {
    return static_cast<int>(get_listeners(chat_id).size());
}

void add_chat_message(i64 chat_id, const Person& p, const std::string& text) {
    if (text.empty() || !p.user_id) return;
    std::lock_guard<std::mutex> lk(mu);
    auto& log = chat_logs[chat_id];
    log.push_back(ChatMsg{p, text, now_ms()});
    if (log.size() > 50) log.erase(log.begin(), log.begin() + (log.size() - 50));
}

std::vector<ChatMsg> get_chat_log(i64 chat_id, int limit) {
    std::lock_guard<std::mutex> lk(mu);
    auto it = chat_logs.find(chat_id);
    if (it == chat_logs.end()) return {};
    auto& log = it->second;
    size_t n = std::min<size_t>(limit, log.size());
    return std::vector<ChatMsg>(log.end() - n, log.end());
}

}  // namespace bot::net
