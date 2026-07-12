# FitFast Downloader

A fast, no-nonsense downloader for **FitGirl Repacks** hosted on **fuckingfast.co**. Paste a FitGirl game page and it grabs every part link for you, then downloads all of them in parallel with 16 connections per file and unpacks the RAR archives when it is done. Built to get past the Cloudflare wall that stops JDownloader and normal browsers.

![FitFast Downloader screenshot](docs/img/screenshot.png)

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078d6)
![Release](https://img.shields.io/github/v/release/DEM9N101/FitFast-Downloader?include_prereleases)
![License](https://img.shields.io/badge/license-MIT-green)
![Downloads](https://img.shields.io/github/downloads/DEM9N101/FitFast-Downloader/total)

---

## Why this exists

FitGirl repacks are usually split into a dozen or more `.rar` parts on fuckingfast.co. That host puts a Cloudflare challenge in front of every file, and it hands the real download link back through a header trick that most download managers do not follow. So JDownloader 2 stalls, the browser throws "blocked", and you sit there clicking eighteen links by hand.

FitFast solves the whole chain:

- It passes the Cloudflare check with a real stealth browser engine, not a spoofed user agent that gets caught.
- It reads the signed download URL out of the response the way the site actually delivers it.
- It hands that URL to aria2, the fastest open download engine there is, split across many connections.

## Features

- **Paste one FitGirl page, get every link.** Drop a `fitgirl-repacks.site` game URL in the top box and hit Fetch. FitFast reads the page and pulls out all the fuckingfast.co parts, main game and bonus content, in order.
- **Or paste links directly.** Already have the list? Paste it and go.
- **Real Cloudflare bypass.** Uses the Camoufox stealth browser engine to clear the challenge that blocks other tools. No manual captcha clicking.
- **Serious speed.** aria2 downloads each file over 16 parallel connections, several files at once. On most connections this saturates your line.
- **Auto re-resolve for slow files.** fuckingfast.co has fast and slow edge servers. If one file gets stuck on a slow one, FitFast quietly grabs a fresh link and resumes from where it left off, so a single bad server does not hold up the batch. No other tool in this space does this.
- **One clean folder per game.** All parts land in a single subfolder named after the game, so your Downloads folder does not turn into a pile of loose `.part01.rar` files.
- **Auto-extract when done.** FitFast unpacks the RAR set for you with a bundled UnRAR. Turn it off if you would rather do it yourself, and optionally delete the archives after a clean extract.
- **Resume anything.** Close the app mid-download, reopen, paste the same links, and it picks up from the exact byte it stopped at.
- **Speed test built in.** One click measures what your line can actually do, so you know whether a slow download is the host or your ISP.
- **Portable.** Download the release, unzip, run. No installer, no admin rights.

## Download and run

1. Go to the [Releases page](https://github.com/DEM9N101/FitFast-Downloader/releases) and download the latest `FitFast-Downloader-win64.zip`.
2. Unzip it anywhere.
3. Run `FitFast.exe`.

On first launch it downloads the stealth browser once (a few hundred MB). After that it starts straight up.

Windows SmartScreen may warn you because the exe is not code-signed. Click "More info" then "Run anyway". The source is all here if you want to read it or build it yourself.

## How to use it

1. Open FitFast.
2. Paste a FitGirl game page URL in the **FitGirl page** box and click **Fetch links**. (Or paste fuckingfast.co links straight into the **Links** box, one per line.)
3. Pick a **Destination** folder. FitFast makes a subfolder named after the game inside it.
4. Click **Start Downloads**.

That is it. Watch the per-file progress, and if auto-extract is on you get a ready-to-install folder at the end.

## Speed tips

- **Concurrent files** decides how many files download at once. More files is not always faster once your line is full. Run the built-in speed test to see your ceiling.
- **Connections per file** defaults to 16, which is plenty for most people. Push it to 24 or 32 only if you have a very fast connection.
- Leave **Auto re-resolve** on. It is the setting that fixes the random 1 MB/s files.
- A wired connection beats Wi-Fi for large multi-gigabyte repacks.

## Run from source

You need Python 3.11+ and the Camoufox stealth browser.

```bash
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m camoufox fetch
.venv\Scripts\python -m app.main
```

`aria2c.exe` and `UnRAR.exe` are already in `vendor/`.

## How it works

For anyone curious about the internals:

1. **Resolve.** A Camoufox (stealth Firefox) tab opens the fuckingfast.co page. Cloudflare's JavaScript challenge runs and passes on its own. FitFast clicks the download control, and the site answers an HTMX request with an `hx-redirect` header pointing at a signed `dl.fuckingfast.co` URL. That signed URL is the real file and it supports HTTP range requests.
2. **Download.** The signed URL goes to an aria2 daemon over RPC, which pulls it with 16 connections and writes with a large disk cache and instant file allocation.
3. **Watch.** A monitor tracks each file's throughput. If one drops far below its peers for long enough, FitFast removes it, resolves a fresh signed URL (often a different, faster edge), and aria2 resumes from the partial using its control file.
4. **Extract.** When the batch finishes, bundled UnRAR unpacks each first-volume `.part01.rar` into the game folder.

## FAQ

**Is this safe?** The code is open. It bundles two well-known tools, aria2 and UnRAR, both unmodified. Nothing phones home.

**Does it work on Mac or Linux?** Windows only for now. The engine is cross platform, so a port is possible later.

**Cloudflare changed something and it broke.** Open an issue. The stealth engine gets updated regularly and usually keeps up.

**It downloaded but did not extract.** Auto-extract needs the bundled UnRAR, which ships in the zip. If you run from source, make sure `vendor/UnRAR.exe` is present, or install WinRAR and FitFast will use that.

## Alternatives

There are a few other FitGirl and fuckingfast downloaders on GitHub. Most are command-line scripts, use fragile `curl_cffi` spoofing that Cloudflare catches, or have no real UI. FitFast is the one with a proper interface, a genuine stealth engine, automatic slow-server recovery, page scraping, and one-click extraction in the same app.

## Disclaimer

FitFast Downloader is an independent, unofficial tool. It is **not affiliated with, endorsed by, or connected to FitGirl, FitGirl Repacks, fuckingfast.co, or any file host** in any way. Those names are used only to describe what the tool is compatible with.

This program does not host, provide, or distribute any files or content. It is a general download client for the fuckingfast.co file host. It only downloads links that you choose to give it. What you download and whether you have the right to do so is entirely your responsibility. Respect the laws where you live and the terms of the sites you use.

The software is provided as is, without warranty of any kind. Use it at your own discretion and your own risk. The authors are not liable for how you use it or for any data loss, legal issue, or damage that results.

## License

MIT for the FitFast code. Bundled third-party tools keep their own licenses: [aria2](https://github.com/aria2/aria2) (GPLv2) and UnRAR (see `vendor/UnRAR-license.txt`, free to redistribute).

---

<sub>Keywords: FitGirl Repacks downloader, fuckingfast downloader, fuckingfast.co downloader, FitGirl repack download manager, download FitGirl repacks fast, fuckingfast batch download, FitGirl multi part rar downloader, bypass Cloudflare download, aria2 game downloader, FitGirl repacks tool, fuckingfast link extractor.</sub>
