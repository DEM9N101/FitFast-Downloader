# Outreach drafts (manual-submit only)

The Reddit account is on cooldown after the spam-filter hit. Everything below is a one-click copy-paste for you when you want it. Do not use the Dem9n101 Reddit account again for at least a week, and even then space posts by more than a day.

---

## 1. r/FitGirlRepack modmail (unblocks the top post + comments)

Go to https://www.reddit.com/message/compose?to=/r/FitGirlRepack and paste:

> **Subject:** Post caught by Reddit's automated spam filter — asking for review
>
> Hi mods,
>
> I posted about a free open-source tool I built for downloading FitGirl repacks past the fuckingfast.co Cloudflare block earlier today, and it looks like Reddit's site-wide automated spam filter removed it (not by you). Would you mind having a look and approving it if it fits the sub?
>
> Post: https://www.reddit.com/r/FitGirlRepack/comments/1uvr2lx/
>
> The tool: https://github.com/DEM9N101/FitFast-Downloader
>
> I noticed similar homebrew tool posts have been kept up in the sub (for example r/FitGirlRepack/comments/1uo78xj), so I hope this one is welcome too. Happy to reword or restructure if I broke any rule I missed.
>
> Thanks for your time.

Also modmail r/CloudFlare and r/jdownloader if you want the other comment placements unblocked, but honestly the top post in r/FitGirlRepack is 90 percent of the value.

---

## 2. Hacker News "Show HN" (biggest single traffic source for niche dev tools)

Go to https://news.ycombinator.com/submit and paste:

**Title:**

> Show HN: FitFast — free FitGirl repack downloader that gets past the Cloudflare block

**URL:**

> https://github.com/DEM9N101/FitFast-Downloader

Then in the comments below the post (once it's submitted), post this as the first reply so people know what it is:

> I built this because JDownloader 2 (the standard tool for grabbing multi-part repacks from fuckingfast.co) started getting blocked with "Blocked by Cloudflare Site-Pro" a month or so ago. The host had switched to an HTMX flow where the real download URL comes back in an `hx-redirect` header after a POST, so vanilla download managers do not see it.
>
> FitFast uses Camoufox (a fingerprint-hardened Firefox) to pass the Cloudflare check and read that header, then hands the direct URL to aria2 for the actual download. There's a small monitor that watches per-file throughput and re-resolves any file stuck on a slow CDN edge with a fresh signed URL, resuming from the partial (this was the single biggest speed win for me).
>
> Packaged as a one-click Windows installer via PyInstaller + Inno Setup. About 46 MB installer. The Camoufox browser (~1 GB) is fetched on first launch with a progress dialog, so the installer stays small.
>
> Windows only for now. Source is MIT. Not affiliated with FitGirl or any host. Happy to answer technical questions.

HN tips:
- Post on a **Tuesday to Thursday, 8am to 10am US Pacific**. That is when new submissions have the best chance of hitting the front page.
- Don't ask for upvotes anywhere — HN detects this and buries the post.
- Reply promptly and technically to any comment in the first 90 minutes.

---

## 3. AlternativeTo (evergreen SEO channel)

Go to https://alternativeto.net/software/jdownloader/ → click "Suggest as alternative" (requires a free account). Fill:

**Name:** FitFast Downloader
**URL:** https://github.com/DEM9N101/FitFast-Downloader
**Category:** Download Managers
**Platforms:** Windows
**License:** Open Source (MIT), Free
**Description:**

> Free open-source Windows download manager built for FitGirl repacks and the fuckingfast.co file host. Uses a stealth browser to bypass the Cloudflare block that stops JDownloader 2 from working, then downloads all multi-part rars in parallel with 16 connections per file and auto-extracts them into one folder. Paste a FitGirl page URL or a list of fuckingfast.co links and it handles the rest.

**Tags:** cloudflare-bypass, download-accelerator, jdownloader-alternative, fitgirl, repack, aria2, open-source

Also list it under **IDM** and **Free Download Manager** as an alternative. Each listing is a separate discovery surface.

---

## 4. GitHub Trending path (organic)

Getting the repo onto GitHub's daily Python trending page requires ~15 stars in a day. If you know a couple of people, a few genuine stars over 24 hours will do it, and the trending page itself sends hundreds of visitors. Do NOT ask on Reddit or Discord ("please star this") — that violates GitHub's terms.

---

## 5. Small forums that actually drive downloads for this niche

- **cs.rin.ru** — has a "software" section, posting there is welcomed if you contribute to threads first. Account needed.
- **1337x forums** — same story.
- **r/Piracy wiki tool list** — get a mod to add FitFast to the wiki. Modmail-only.

---

## 6. Landing page (already live, no action needed from you)

- https://dem9n101.github.io/FitFast-Downloader/ — the GitHub Pages site. Full SEO metadata, keyword-loaded FAQ, screenshots. Google will index it within a few days. Fresh queries like "blocked by cloudflare fitgirl fix" or "jdownloader2 blocked cloudflare fuckingfast" should surface it once indexed.
