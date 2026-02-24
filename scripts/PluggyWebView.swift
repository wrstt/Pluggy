import AppKit
import Foundation
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private var window: NSWindow?
    private var webView: WKWebView?
    private var timer: Timer?
    private var startupDate = Date()
    private var networkHits = 0
    private var checkInFlight = false
    private var didLoadMain = false

    private let targetURL = URL(string: "http://127.0.0.1:3000")!
    private let minimumSplashSeconds: TimeInterval = 2.8
    private let fallbackOpenSeconds: TimeInterval = 60.0
    private let readinessTimeoutSeconds: TimeInterval = 35.0

    func applicationDidFinishLaunching(_ notification: Notification) {
        startupDate = Date()
        setupWindow()
        loadSplash()
        startLauncher()
        startReadinessLoop()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
    }

    private func setupWindow() {
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1360, height: 900)
        let width: CGFloat = min(1360, max(980, screenRect.width * 0.9))
        let height: CGFloat = min(860, max(700, screenRect.height * 0.9))
        let originX = screenRect.midX - (width / 2)
        let originY = screenRect.midY - (height / 2)
        let rect = NSRect(x: originX, y: originY, width: width, height: height)

        let style: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]
        let window = NSWindow(contentRect: rect, styleMask: style, backing: .buffered, defer: false)
        window.title = "Pluggy"
        window.minSize = NSSize(width: 960, height: 620)
        window.isReleasedWhenClosed = false

        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        let webView = WKWebView(frame: rect, configuration: config)
        webView.navigationDelegate = self
        webView.autoresizingMask = [.width, .height]
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)

        self.window = window
        self.webView = webView
    }

    private func loadSplash() {
        let html = """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width,initial-scale=1" />
          <title>Pluggy Launching</title>
          <style>
            :root { color-scheme: dark; }
            body {
              margin: 0;
              min-height: 100vh;
              font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
              display: grid;
              place-items: center;
              background: radial-gradient(circle at 20% 20%, #2a354a 0%, #10141e 55%, #090c13 100%);
              color: #eef2ff;
            }
            .card {
              width: min(560px, 92vw);
              border-radius: 16px;
              border: 1px solid rgba(255,255,255,0.16);
              background: rgba(16, 20, 30, 0.72);
              backdrop-filter: blur(10px);
              padding: 28px 24px;
              box-shadow: 0 28px 90px rgba(4, 8, 20, 0.45);
            }
            .title {
              font-size: 26px;
              font-weight: 700;
              letter-spacing: -0.02em;
              margin: 0;
            }
            .subtitle {
              margin: 8px 0 18px;
              color: rgba(232, 238, 255, 0.84);
              font-size: 14px;
            }
            .progress-wrap {
              height: 12px;
              border-radius: 999px;
              border: 1px solid rgba(255,255,255,0.2);
              overflow: hidden;
              background: rgba(0, 0, 0, 0.25);
            }
            .progress {
              height: 100%;
              width: 12%;
              border-radius: 999px;
              background: linear-gradient(90deg, #53e2ff 0%, #6df3c8 50%, #ffe083 100%);
              transition: width .24s ease;
            }
            .status {
              margin-top: 12px;
              font-size: 13px;
              color: rgba(232, 238, 255, 0.9);
            }
            .hint {
              margin-top: 10px;
              font-size: 12px;
              color: rgba(210, 220, 245, 0.7);
            }
          </style>
        </head>
        <body>
          <section class="card">
            <h1 class="title">Pluggy</h1>
            <p class="subtitle">Starting services and preparing your workspace...</p>
            <div class="progress-wrap"><div class="progress" id="bar"></div></div>
            <p class="status" id="status">Starting backend...</p>
            <p class="hint">This screen will close automatically when Pluggy is ready.</p>
          </section>
          <script>
            window.__pluggyUpdate = (progress, statusText) => {
              const bar = document.getElementById("bar");
              const status = document.getElementById("status");
              if (bar) bar.style.width = Math.max(0, Math.min(100, progress)) + "%";
              if (status && statusText) status.textContent = statusText;
            };
          </script>
        </body>
        </html>
        """
        webView?.loadHTMLString(html, baseURL: nil)
    }

    private func startLauncher() {
        guard let launcherPath = Bundle.main.path(forResource: "launch_platswap", ofType: "sh") else {
            return
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [launcherPath]
        var env = ProcessInfo.processInfo.environment
        env["PLUGGY_WEBVIEW"] = "1"
        process.environment = env

        let devNull = FileHandle(forWritingAtPath: "/dev/null")
        process.standardOutput = devNull
        process.standardError = devNull
        process.standardInput = nil

        do {
            try process.run()
        } catch {
            // If this fails, the readiness loop will timeout and still attempt to open localhost.
        }
    }

    private func startReadinessLoop() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.45, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    private func tick() {
        guard !didLoadMain else { return }

        let elapsed = Date().timeIntervalSince(startupDate)
        let timedOut = elapsed >= readinessTimeoutSeconds
        let splashTimedOut = elapsed >= fallbackOpenSeconds

        var progress = min(95.0, 12.0 + (elapsed * 2.0))
        var status = "Starting backend..."
        if progress >= 42 { status = "Starting frontend..." }
        if progress >= 68 { status = "Warming providers..." }
        if progress >= 92 { status = "Opening Pluggy..." }

        if timedOut || splashTimedOut {
            progress = 100
            status = "Opening Pluggy..."
            updateSplash(progress: progress, status: status)
            openMainIfReady(force: true)
            return
        }

        updateSplash(progress: progress, status: status)
        checkReachability()
    }

    private func checkReachability() {
        guard !checkInFlight, !didLoadMain else { return }
        checkInFlight = true

        var request = URLRequest(url: targetURL)
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = 0.9

        URLSession.shared.dataTask(with: request) { [weak self] _, _, error in
            guard let self else { return }
            DispatchQueue.main.async {
                self.checkInFlight = false
                if error == nil {
                    self.networkHits += 1
                }
                self.openMainIfReady(force: false)
            }
        }.resume()
    }

    private func openMainIfReady(force: Bool) {
        guard !didLoadMain else { return }
        let elapsed = Date().timeIntervalSince(startupDate)
        let minSatisfied = elapsed >= minimumSplashSeconds
        let ready = networkHits >= 2
        guard force || (ready && minSatisfied) else { return }

        didLoadMain = true
        timer?.invalidate()
        timer = nil
        updateSplash(progress: 100, status: "Ready. Opening Pluggy...")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            var request = URLRequest(url: self.targetURL)
            request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
            self.webView?.load(request)
        }
    }

    private func updateSplash(progress: Double, status: String) {
        let safe = status.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'")
        let js = "window.__pluggyUpdate && window.__pluggyUpdate(\(String(format: "%.2f", progress)), '\(safe)');"
        webView?.evaluateJavaScript(js, completionHandler: nil)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
