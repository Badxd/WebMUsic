// Mini "listen-together room" webapp: a small HTTP server serving a
// static page + a JSON polling API (no websocket — this project has
// no websocket/async-HTTP-server dependency, and hand-rolling one
// safely in a single pass is far riskier than polling every 1-2s,
// which gives the same live-feeling result with a fraction of the
// code and failure surface).
//
// Read-mostly by design: Queue/TgCall stay the single source of
// truth. This only (a) reports that state as JSON and (b) forwards a
// handful of admin-gated controls into the exact same TgCall methods
// /pause /resume /skip already call.
#pragma once
#include <atomic>
#include <thread>

namespace bot::net {

class WebServer {
public:
    // Starts the accept loop on its own thread. Safe to call even if
    // it fails to bind — logs a warning and the bot keeps running
    // without the website, same as every other optional feature here.
    void start(const std::string& host, int port);
    void stop();
    ~WebServer();

private:
    void accept_loop(int listen_fd);
    std::thread thread_;
    std::atomic<bool> running_{false};
    int listen_fd_ = -1;
};

WebServer& web();

}  // namespace bot::net
