// Small additive state for the mini webapp room. Deliberately NOT
// persisted to the database — this is a live "who's here right now" /
// "last few messages" view, not saved chat history or a friends/
// profile system. It all disappears once the room empties out.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace bot::net {

using i64 = std::int64_t;

struct Person {
    i64 user_id = 0;
    std::string name;
    std::string username;
    std::string photo_url;
};

struct ChatMsg {
    Person person;
    std::string text;
    i64 ts_ms = 0;
};

// Every incoming Message carries chat.title — dispatch_message() caches
// it here so the web API can show the real group name without needing
// a "get chat by id" call the tg::Client interface doesn't have.
void cache_chat_title(i64 chat_id, const std::string& title);
std::string get_chat_title(i64 chat_id);

// Called whenever a viewer polls /api/room/<chat_id> with their
// Telegram identity attached. "Here" = polled within the last 30s.
void touch_listener(i64 chat_id, const Person& p);
std::vector<Person> get_listeners(i64 chat_id);
int listener_count(i64 chat_id);

void add_chat_message(i64 chat_id, const Person& p, const std::string& text);
std::vector<ChatMsg> get_chat_log(i64 chat_id, int limit = 30);

}  // namespace bot::net
