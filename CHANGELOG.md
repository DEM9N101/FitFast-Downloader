# Changelog

## 1.2.0

The big one: downloads are far faster and far more reliable. If you were seeing
speeds crawl along at 1 to 2 MB/s, files failing for no clear reason, or an
error mentioning "invalid range header", this release fixes it.

### Fixed: the range error that was wrecking speeds

fuckingfast.co replies incorrectly when a file is requested in several pieces
at once. It sends the right data but labels it wrongly, and the download engine
rejects the mismatch. The result was that only one piece of each file ever
worked, so downloads got slower and slower and eventually failed. One test run
produced 194 of these errors and nothing else.

FitFast now downloads each file as a single stream and gets its speed from
downloading several files at the same time instead. Measured on real repack
parts: **1 to 2 MB/s before, 32 MB/s after, with zero errors.**

Resuming an interrupted download still works exactly as before.

### Fixed: downloads no longer give up on themselves

- A file that fails now automatically gets a fresh link and carries on from
  where it stopped, up to three times, instead of being marked dead.
- Removed a setting that cut off any download whose speed dipped, which could
  turn a brief slow patch into a batch of failed files.

### Fixed: no more freezing your PC

Preparing links runs a hidden browser, and each one uses close to a gigabyte of
memory. FitFast previously started several without checking, which could run a
machine out of memory.

- FitFast now checks free memory first and quietly uses fewer, telling you why.
- Each browser is much lighter: images, video and fonts are no longer loaded,
  since only the link matters. This also made preparing links faster, roughly
  10 seconds instead of 15.
- Browsers restart periodically so memory stays flat across a long download.

### Faster on big batches

Links are now prepared several at a time instead of one after another. On a
large repack the download engine used to sit idle waiting for the next link.
There is a new **Resolvers** setting for this, and FitFast lowers it
automatically if memory is tight.

### Clearer progress

The status line now shows how many files are done, how many links are ready,
how much has actually been downloaded, current and peak speed, and a time
estimate. Previously the totals only counted the few files prepared so far,
which made progress look wrong.

### Settings

- **Connections/file** now defaults to 1 and should stay there for
  fuckingfast.co. The tooltip explains why.
- **Concurrent files** is now the main speed dial, defaulting to 4. Worth
  trying 2 and 8 to see which suits your connection, since hosts slow you down
  past a certain number of streams.
- **Resolvers** is new, defaulting to 2.

Your existing settings are kept, and anything new is filled in automatically.

## 1.1.0

- Click-to-install Windows installer, no admin needed
- Success and error notifications
- Hover explanations on every setting
- Copyable error reports plus a log file, for reporting problems
- Help and About screen
- Rewritten guide with screenshots and troubleshooting

## 1.0.0

- First release: paste FitGirl page or fuckingfast.co links, download every
  part, auto-unpack into one folder per game
