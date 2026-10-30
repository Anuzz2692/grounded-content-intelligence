"""A tiny pretend company website (Example Co) so the studio can be tried without internet access."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FILLER = ("Example Co designs and installs home solar systems and battery backups. A site visit comes first, so the design fits the roof, "
          "the household's usage and the local grid rules. ") * 3

PAGES = {
    "/": ("Example Co | Home solar and batteries",
          'Welcome to Example Co. <a href="/battery-backup">Battery backup</a> <a href="/site-visit">Site visits</a> '
          '<a href="/warranty">Warranty</a> <a href="/solar-panels">Solar panels</a> <a href="/about">About us</a>'),
    "/battery-backup": ("Battery backup | Example Co",
                        "A battery backup stores electricity so a home can keep essential circuits running during an outage. "
                        "Installers size the battery after reviewing how the household uses power and which circuits matter most. "
                        "Backup time depends on the battery size and what is connected. " + FILLER),
    "/site-visit": ("What happens at a site visit | Example Co",
                    "At a site visit an installer checks the roof, the electrical panel and the available space. "
                    "The visit also covers the household's usage, so the quote reflects the home rather than a template. "
                    "Visits are booked online or by phone. " + FILLER),
    "/warranty": ("Warranty and support | Example Co",
                  "Example Co supports each installation with a written warranty and a support line. Warranty terms differ between "
                  "panels, inverters and batteries, and are set out in the quote. " + FILLER),
    "/solar-panels": ("Solar panels | Example Co",
                      "Solar panels turn sunlight into electricity. Output depends on roof direction, shade and season. "
                      "An installer estimates output for your roof during the site visit. " + FILLER),
    "/about": ("About Example Co", "Example Co is a fictional company used to demonstrate Grounded Content Studio. " + FILLER),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        page = PAGES.get(self.path.split("?")[0])
        if page is None:
            self.send_response(404)
            self.end_headers()
            return
        title, body = page
        html = f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>{body}</p></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, *args):
        pass


def make_server(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
