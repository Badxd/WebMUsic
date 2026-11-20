#include "httpserver.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstring>
#include <fstream>
#include <map>
#include <nlohmann/json.hpp>
#include <sstream>

#include "../cmd/common.hpp"
#include "../core/calls.hpp"
#include "../core/config.hpp"
#include "../core/log.hpp"
#include "../core/queue.hpp"
#include "../core/types.hpp"
#include "../core/util.hpp"
#include "../db/db.hpp"
#include "roomstate.hpp"

namespace bot::net {
namespace {

using json = nlohmann::json;

// ── tiny HTTP helpers (no server library is linked in this project —
//    raw sockets + minimal HTTP/1.1 parsing is the lowest-risk way to
//    add this without a new heavy dependency) ────────────────────────

std::string url_decode(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == '%' && i + 2 < s.size()) {
            int v = 0;
            std::istringstream(s.substr(i + 1, 2)) >> std::hex >> v;
            out += static_cast<char>(v);
            i += 2;
        } else if (s[i] == '+') {
            out += ' ';
        } else {
            out += s[i];
        }
    }
    return out;
}

std::map<std::string, std::string> parse_query(const std::string& qs) {
    std::map<std::string, std::string> out;
    std::istringstream ss(qs);
    std::string pair;
    while (std::getline(ss, pair, '&')) {
        auto eq = pair.find('=');
        if (eq == std::string::npos) continue;
        out[url_decode(pair.substr(0, eq))] = url_decode(pair.substr(eq + 1));
    }
    return out;
}

struct Request {
    std::string method, path, query, body;
    std::map<std::string, std::string> params;  // merged query params
};

struct Response {
    int status = 200;
    std::string content_type = "application/json; charset=utf-8";
    std::string body;
};

bool ends_with(const std::string& s, const std::string& suffix) {
    return s.size() >= suffix.size() && s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

std::string content_type_for(const std::string& path) {
    if (ends_with(path, ".html")) return "text/html; charset=utf-8";
    if (ends_with(path, ".css")) return "text/css; charset=utf-8";
    if (ends_with(path, ".js")) return "application/javascript; charset=utf-8";
    return "application/octet-stream";
}

bool read_file(const std::string& path, std::string& out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::ostringstream ss;
    ss << f.rdbuf();
    out = ss.str();
    return true;
}

Person person_from_params(const std::map<std::string, std::string>& p) {
    Person person;
    auto get = [&](const char* k) { auto it = p.find(k); return it != p.end() ? it->second : std::string(); };
    try { person.user_id = get("user_id").empty() ? 0 : std::stoll(get("user_id")); } catch (...) {}
    person.name = get("name").empty() ? "Guest" : get("name").substr(0, 40);
    person.username = get("username");
    person.photo_url = get("photo");
    return person;
}

json person_json(const Person& p) {
    return json{{"user_id", p.user_id}, {"name", p.name}, {"username", p.username}, {"photo_url", p.photo_url}};
}

json build_state(i64 chat_id, const Person& viewer) {
    if (viewer.user_id) touch_listener(chat_id, viewer);

    bool live = db().get_call(chat_id);
    TrackPtr cur = queue().get_current(chat_id);

    json song = nullptr;
    if (live && cur) {
        song = json{
            {"title", cur->title},
            {"url", cur->url},
            {"duration_sec", cur->duration_sec},
            {"thumbnail", cur->thumbnail},
            {"requested_by", cur->user},
            {"seek", cur->position()},
            {"playing", cur->paused_at_ms == 0},
        };
    }

    json q = json::array();
    for (auto& t : queue().get_queue(chat_id))
        if (t) q.push_back(json{{"title", t->title}, {"duration", t->duration}, {"requested_by", t->user}});

    json people = json::array();
    for (auto& p : get_listeners(chat_id)) people.push_back(person_json(p));

    json chat = json::array();
    for (auto& m : get_chat_log(chat_id))
        chat.push_back(json{{"person", person_json(m.person)}, {"text", m.text}, {"ts", m.ts_ms}});

    return json{
        {"chat_id", chat_id},
        {"chat_name", get_chat_title(chat_id)},
        {"active", live && cur != nullptr},
        {"song", song},
        {"queue", q},
        {"listeners", listener_count(chat_id)},
        {"listener_people", people},
        {"chat_log", chat},
        {"is_admin", viewer.user_id ? is_admin(chat_id, viewer.user_id) : false},
    };
}

i64 parse_chat_id(const std::string& s) {
    // Clean short links encode a negative group id as "N<abs>"
    // (matches the Python sibling projects' startapp convention).
    try {
        if (!s.empty() && s[0] == 'N') return -std::stoll(s.substr(1));
        return std::stoll(s);
    } catch (...) {
        return 0;
    }
}

Response route(const Request& req) {
    Response res;

    if (req.method == "GET" && (req.path == "/" || req.path == "/index.html")) {
        if (read_file("www/index.html", res.body)) { res.content_type = "text/html; charset=utf-8"; return res; }
        res.status = 500; res.body = "index.html missing"; res.content_type = "text/plain"; return res;
    }
    if (req.method == "GET" && req.path == "/favicon.ico") { res.status = 204; res.body = ""; return res; }
    if (req.method == "GET" && util::starts_with(req.path, "/static/") && req.path.find("..") == std::string::npos) {
        std::string file = "www" + req.path;
        if (read_file(file, res.body)) { res.content_type = content_type_for(file); return res; }
        res.status = 404; res.body = "not found"; res.content_type = "text/plain"; return res;
    }

    if (util::starts_with(req.path, "/api/room/")) {
        i64 chat_id = parse_chat_id(req.path.substr(10));
        Person viewer = person_from_params(req.params);
        res.body = build_state(chat_id, viewer).dump();
        return res;
    }

    if (req.method == "POST" && util::starts_with(req.path, "/api/control/")) {
        i64 chat_id = parse_chat_id(req.path.substr(14));
        auto it_action = req.params.find("action");
        auto it_uid = req.params.find("user_id");
        if (it_action == req.params.end() || it_uid == req.params.end()) {
            res.status = 400; res.body = json{{"ok", false}, {"error", "missing_params"}}.dump(); return res;
        }
        i64 user_id = 0;
        try { user_id = std::stoll(it_uid->second); } catch (...) {}
        if (!user_id || !is_admin(chat_id, user_id)) {
            res.status = 403; res.body = json{{"ok", false}, {"error", "not_admin"}}.dump(); return res;
        }
        if (!db().get_call(chat_id)) {
            res.status = 400; res.body = json{{"ok", false}, {"error", "not_playing"}}.dump(); return res;
        }
        const std::string& action = it_action->second;
        if (action == "pause") bad().pause(chat_id);
        else if (action == "resume") bad().resume(chat_id);
        else if (action == "skip") bad().play_next(chat_id);
        else if (action == "stop") bad().stop(chat_id);
        else { res.status = 400; res.body = json{{"ok", false}, {"error", "unknown_action"}}.dump(); return res; }
        res.body = json{{"ok", true}}.dump();
        return res;
    }

    if (util::starts_with(req.path, "/api/chat/")) {
        i64 chat_id = parse_chat_id(req.path.substr(10));
        if (req.method == "POST") {
            Person p = person_from_params(req.params);
            std::string text;
            try { text = json::parse(req.body).value("text", ""); } catch (...) {}
            if (text.size() > 300) text = text.substr(0, 300);
            if (!p.user_id || text.empty()) {
                res.status = 400; res.body = json{{"ok", false}}.dump(); return res;
            }
            add_chat_message(chat_id, p, text);
            res.body = json{{"ok", true}}.dump();
            return res;
        }
        json out = json::array();
        for (auto& m : get_chat_log(chat_id))
            out.push_back(json{{"person", person_json(m.person)}, {"text", m.text}, {"ts", m.ts_ms}});
        res.body = out.dump();
        return res;
    }

    res.status = 404;
    res.body = json{{"error", "not_found"}}.dump();
    return res;
}

// ── minimal HTTP/1.1 request read + response write ──────────────────

bool read_request(int fd, Request& req) {
    std::string buf;
    char chunk[4096];
    size_t header_end = std::string::npos;
    while (header_end == std::string::npos) {
        ssize_t n = recv(fd, chunk, sizeof(chunk), 0);
        if (n <= 0) return false;
        buf.append(chunk, n);
        header_end = buf.find("\r\n\r\n");
        if (buf.size() > 1 << 20) return false;  // 1 MB header guard
    }
    std::string head = buf.substr(0, header_end);
    std::string rest = buf.substr(header_end + 4);

    std::istringstream hs(head);
    std::string line;
    std::getline(hs, line);
    std::istringstream rl(line);
    std::string full_path;
    rl >> req.method >> full_path;  // HTTP version after this isn't needed
    auto qpos = full_path.find('?');
    req.path = qpos == std::string::npos ? full_path : full_path.substr(0, qpos);
    req.query = qpos == std::string::npos ? "" : full_path.substr(qpos + 1);
    req.params = parse_query(req.query);

    size_t content_length = 0;
    while (std::getline(hs, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::string key = util::lower(util::trim(line.substr(0, colon)));
        std::string val = util::trim(line.substr(colon + 1));
        if (key == "content-length") { try { content_length = std::stoul(val); } catch (...) {} }
    }

    while (rest.size() < content_length) {
        ssize_t n = recv(fd, chunk, sizeof(chunk), 0);
        if (n <= 0) break;
        rest.append(chunk, n);
    }
    req.body = rest.substr(0, content_length);
    return true;
}

void write_response(int fd, const Response& res) {
    static const std::map<int, std::string> reasons = {
        {200, "OK"}, {204, "No Content"}, {400, "Bad Request"},
        {403, "Forbidden"}, {404, "Not Found"}, {500, "Internal Server Error"},
    };
    auto it = reasons.find(res.status);
    std::ostringstream out;
    out << "HTTP/1.1 " << res.status << " " << (it != reasons.end() ? it->second : "") << "\r\n"
        << "Content-Type: " << res.content_type << "\r\n"
        << "Content-Length: " << res.body.size() << "\r\n"
        << "Access-Control-Allow-Origin: *\r\n"
        << "Connection: close\r\n\r\n"
        << res.body;
    std::string s = out.str();
    send(fd, s.data(), s.size(), 0);
}

void handle_connection(int fd) {
    Request req;
    if (read_request(fd, req)) {
        try {
            write_response(fd, route(req));
        } catch (const std::exception& e) {
            Response r; r.status = 500; r.content_type = "application/json";
            r.body = json{{"error", e.what()}}.dump();
            write_response(fd, r);
        }
    }
    close(fd);
}

}  // namespace

void WebServer::start(const std::string& host, int port) {
    listen_fd_ = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd_ < 0) { log::warn("webapp: socket() failed"); return; }

    int opt = 1;
    setsockopt(listen_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    addr.sin_addr.s_addr = host.empty() || host == "0.0.0.0" ? INADDR_ANY : inet_addr(host.c_str());

    if (bind(listen_fd_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        log::warn("webapp: bind() failed on port " + std::to_string(port) + " — mini webapp disabled, bot continues without it.");
        close(listen_fd_);
        listen_fd_ = -1;
        return;
    }
    if (listen(listen_fd_, 64) < 0) {
        log::warn("webapp: listen() failed");
        close(listen_fd_);
        listen_fd_ = -1;
        return;
    }

    running_ = true;
    thread_ = std::thread([this] { accept_loop(listen_fd_); });
    log::info("Mini webapp running on :" + std::to_string(port) + " \u2705");
}

void WebServer::accept_loop(int listen_fd) {
    while (running_) {
        sockaddr_in client{};
        socklen_t len = sizeof(client);
        int fd = accept(listen_fd, reinterpret_cast<sockaddr*>(&client), &len);
        if (fd < 0) {
            if (!running_) break;
            continue;
        }
        std::thread(handle_connection, fd).detach();
    }
}

void WebServer::stop() {
    running_ = false;
    if (listen_fd_ >= 0) { shutdown(listen_fd_, SHUT_RDWR); close(listen_fd_); listen_fd_ = -1; }
    if (thread_.joinable()) thread_.join();
}

WebServer::~WebServer() { stop(); }

WebServer& web() { static WebServer w; return w; }

}  // namespace bot::net
