# I sat down to see if context engines actually help

I did not start this week wanting a paper. I started it because Delphi was losing to Nia and to grep, and the last time we measured that we did it badly. Same queries twice, different top tens. Gold sitting in the prompt. A 95% DS-1000 number I do not want anyone repeating. I wanted to know, as a person who actually opens gin and pytest at 1am, whether the index is doing anything I cannot do with `rg`.

So I asked three questions a human would type, on pinned commits, and I also ran the boring bench.

## Three questions

**Gin.** Why does my JSON get HTML-escaped, and how do I turn it off?

Delphi returned `render/json.go` in 5.9 seconds. Nia returned it in 12, plus a paragraph about `PureJSON`. Grep returned it in 30 milliseconds, buried under `tree_test.go` because the word "json" lives everywhere. All three found the file. Only one of them was fast enough that I would not have already opened the file myself.

**Tokio.** If I drop a `JoinHandle`, does the spawned task keep running?

Same story. Delphi 4.7s, Nia 13s, grep 0.12s. Everyone landed on the task module. Nia quoted the docs at me: drop detaches, the task keeps going, the return value is gone. That is the useful sentence. Grep gave me 37 hits in `join.rs` and left me to read.

**Pytest.** Where is the logic that rewrites asserts into those long failure messages?

This is the one that changed my mind about "Nia won." Delphi put `src/_pytest/assertion/rewrite.py` first. Grep put it third, after the test file and the changelog, which is exactly what string overlap does. Nia wrote a confident explanation of `rewrite_asserts` and `AssertionRewritingHook` and never put `rewrite.py` in the file list it handed back. The prose was right. The retrieval was not. If you grade the paragraph, Nia wins. If you grade the path, it missed.

That is the whole research question, in one repo. Does the engine help the agent, or does it help the demo?

## What the bench says so far

I threw out the old split. New salt, `delphi-round3-v1`, 75 development cases I am allowed to look at, 282 I am not. Queries are the official ARB JSON, sorted keys, no gold. File text comes from `git show` on the exact commit, not from some truncated chunk dump.

July Delphi, the stack that has been sitting on port 20742 for three weeks: **MRR 0.285, recall@5 0.427, recall@20 0.544, BCY@8k 0.313**. Official BM25 on the same git corpus: **0.144 / 0.173 / 0.391 / 0.104**. So the index is not theater. It is better than BM25 by a lot, on the split I am allowed to tune against.

It is also not done. A third of the cases never see gold in the top 20. Delphi always returns 20 files, so that is a real hole. Comment-to-context is where it goes to die: 48% any-gold@20. The engine loves the review file you already pasted and never walks to `enums.rs` or `eslint.config.js`. I wrote a demotion rule for that and I have not yet proven it does not break the other workflows. Until r3b finishes indexing, that patch stays a hypothesis.

I nearly published a fake Nia comparison by accident. Its manifest had 68
`indexed` rows, which looked right, but only 32 of those snapshots belonged to
this split. The runner would have silently skipped 39 of 75 cases. I cancelled
it after 14, added a coverage preflight that now refuses partial corpora, and
started a clean 68-snapshot upload under one account. I also gave up on the
Windows box and moved lexical back to this laptop. Neither number exists yet.

## The part that made me angry

I repeated eight Delphi queries ten times each. The exact top-ten list matched
31% of the time. Mean Jaccard was 0.76 and Kendall tau was 0.96: much of the
neighborhood survived, but membership and order both moved. Embeddings are not
the main villain. Over 20 repeats, OpenAI small jittered by as much as
2.3e-4 cosine distance without changing a top ten; Gemini came back bitwise
identical. The bigger dance is HyDE and listwise GPT-4o resampling, plus HNSW,
plus ties broken by whoever arrived first. We cached and seeded the LLM calls
on master. I have not measured the patched stack yet. A 31% exact-list rate is
still enough to stop believing single-run leaderboards.

## What I think I believe tonight

Grep is the right first tool. It is honest about what it is. A context engine earns its keep when the question is not a string, when the gold file does not contain the words you typed, when a review comment points at an implementation two directories away. That is comment-to-context, and that is where we are worst.

Nia is a writer that retrieves. Delphi is a retriever that sometimes writes. If you let the writer grade itself, you will ship the wrong one.

I am not claiming SOTA. I am claiming we finally have a split I am not embarrassed to put in a paper, a BM25 number that uses the official ranker, a failure mode I can point at with files, and three questions I actually asked. The rest has to finish before I let anyone say we won.

---

*Numbers from `new/round3/` on 2026-08-23, America/Los_Angeles. July Delphi on the frozen OpenAI 3-small stack. BM25 via official ARB chunking on canonical git. Vignettes on gin `64ead9e`, Tokio `25e7f26`, pytest `0c80a1c`.*
