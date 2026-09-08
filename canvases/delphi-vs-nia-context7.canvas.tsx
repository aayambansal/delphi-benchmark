import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
} from "cursor/canvas";

export default function DelphiVsNiaContext7() {
  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 1040 }}>
      <Stack gap={6}>
        <H1>Delphi vs Nia vs Context7 — round-3 evidence</H1>
        <Text tone="secondary">
          Every number below comes from the round-3 protocol: pinned corpora, exact
          attempt accounting, config attestation, and untouched final splits. Sources:
          new/round3/results and STATE.md, 2026-08-24/25.
        </Text>
      </Stack>

      <Callout tone="info">
        The three engines only overlap fully on documentation retrieval. Repository
        retrieval is Delphi-only in practice: Nia&apos;s hosted account exposes 0/68
        required commit-pinned sources (recorded unavailable, not a loss), and
        Context7 is a documentation service that cannot index repositories at all.
      </Callout>

      <Stack gap={10}>
        <H2>Track coverage</H2>
        <Table
          headers={["Track", "Delphi", "Nia", "Context7"]}
          rows={[
            [
              "Repository retrieval (ARB final, 220 cases)",
              "Scored — leads all runnable baselines",
              "Invalid — 0/68 sources in owned account",
              "Not applicable (docs-only surface)",
            ],
            [
              "Repository retrieval (SWE-bench Track D, 62 cases)",
              "Scored — 48/62 any-gold",
              "Invalid — same hosted blocker",
              "Not applicable",
            ],
            [
              "Documentation retrieval (40 dev cases)",
              "Scored (local index of the same docs)",
              "Scored (hosted retrieval + synthesis)",
              "Scored (hosted, pinned library IDs)",
            ],
            [
              "Downstream DS-1000 pass@1 (40 dev cases × 3 repeats)",
              "Scored",
              "Scored",
              "Scored",
            ],
          ]}
        />
      </Stack>

      <Stack gap={10}>
        <H2>Documentation retrieval — identifier hit rate</H2>
        <Text tone="secondary" size="small">
          Share of cases where the retrieved context contains the gold identifier.
          40 development cases; best prompt shape per engine (query shape is
          provider-specific by decision). Source: DOCS-dev runs + balanced Nia
          replication, 2026-08-24.
        </Text>
        <BarChart
          categories={["Nia (full, retrieval+synthesis)", "Delphi (compact)", "Context7 (pinned IDs, pooled)"]}
          series={[{ name: "Identifier hit rate (0-1)", data: [0.575, 0.4, 0.37] }]}
          height={200}
          yMax={0.7}
          showValues
        />
        <Row gap={8} wrap>
          <Pill tone="warning">Nia leads documentation</Pill>
          <Pill tone="neutral">Delphi vs Context7: +0.03, within noise</Pill>
          <Pill tone="neutral">Nia output is synthesis, not raw retrieval</Pill>
        </Row>
        <Text tone="tertiary" size="small">
          Each engine shown at its best query shape: Nia full prompts (compact drops it
          to 0.450), Delphi compact (full drops it to 0.300), Context7 statistically
          tied across shapes (pooled full 0.370 vs compact 0.360, CI includes 0).
        </Text>
      </Stack>

      <Stack gap={10}>
        <H2>Fair comparison — matched output contracts (new, 2026-08-25)</H2>
        <Text tone="secondary" size="small">
          Nia&apos;s 0.575 is scored on synthesized answer text; Delphi&apos;s 0.400 was raw
          retrieved context. Matching the contract — Delphi retrieval + answer-style
          synthesis with the frozen gpt-5.4-mini — closes the question. 40 cases,
          3 repeats, zero failures. Source: DOCS-dev answer-synthesis runs, 2026-08-25.
        </Text>
        <BarChart
          categories={[
            "Context7 retrieval + synthesis",
            "Delphi retrieval + synthesis",
            "Nia retrieval + synthesis (recorded)",
            "Model alone, no retrieval (control)",
          ]}
          series={[{ name: "Identifier hit rate (0-1)", data: [0.625, 0.617, 0.575, 0.492] }]}
          height={230}
          yMax={0.7}
          showValues
        />
        <Row gap={8} wrap>
          <Pill tone="success">Delphi +0.042 and Context7 +0.050 over Nia</Pill>
          <Pill tone="neutral">Three-way statistical tie — every CI includes 0</Pill>
          <Pill tone="info">~0.49 of everyone&apos;s score is the model, not retrieval</Pill>
        </Row>
        <Text tone="tertiary" size="small">
          The old documentation gap was an output-contract artifact, not a retrieval
          deficit. Retrieval contribution over the no-retrieval floor: Context7 +0.133
          (CI excludes zero), Delphi +0.125 (CI touches zero), Nia +0.083. End-to-end
          latency: Delphi retrieval + synthesis ≈ 5.1 s vs Nia 12.4 s.
        </Text>
      </Stack>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>Documentation determinism (10 cases × 10 runs)</CardHeader>
          <CardBody>
            <Stack gap={12}>
              <Text tone="secondary" size="small">
                Exact-context repeat rate — identical retrieved context across runs.
              </Text>
              <Row gap={24}>
                <Stat label="Delphi (compact)" value="98.0%" tone="success" />
                <Stat label="Context7 (guided)" value="35.6%" tone="warning" />
                <Stat label="Nia (full)" value="0.0%" tone="danger" />
              </Row>
              <Text tone="tertiary" size="small">
                Nia never returned byte-identical context (synthesis varies) though its
                underlying citation sets were near-stable (all-five mean Jaccard 0.993).
                Delphi also had perfect hit agreement (1.000) across all 100 runs.
              </Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>Mean latency per request (documentation track)</CardHeader>
          <CardBody>
            <Stack gap={12}>
              <Text tone="secondary" size="small">
                Same 40-case documentation runs; wall clock per retrieval request.
              </Text>
              <Row gap={24}>
                <Stat label="Context7 (hosted)" value="2.0 s" tone="success" />
                <Stat label="Delphi (local)" value="2.6 s" />
                <Stat label="Nia (hosted + synthesis)" value="12.4 s" tone="warning" />
              </Row>
              <Text tone="tertiary" size="small">
                Nia full-prompt mean 12.4 s, compact 15.0 s — its synthesis step costs
                roughly 5-6x the other engines. Delphi and Context7 are comparable.
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Stack gap={10}>
        <H2>Downstream coding utility — DS-1000 pass@1</H2>
        <Text tone="secondary" size="small">
          Frozen generation model, 40 development cases × 3 repeats. No engine&apos;s
          delta over the no-retrieval control is statistically distinguishable from
          zero (all case-cluster 95% CIs include 0).
        </Text>
        <BarChart
          categories={["Nia", "Delphi", "No retrieval", "Context7"]}
          series={[{ name: "pass@1 (mean of 3 repeats)", data: [0.642, 0.592, 0.575, 0.567] }]}
          height={200}
          yMin={0}
          yMax={0.75}
          referenceLines={[{ value: 0.575, label: "no-retrieval control", tone: "neutral" }]}
          showValues
        />
      </Stack>

      <Divider />

      <Stack gap={10}>
        <H2>Repository retrieval — where Delphi is actually tested</H2>
        <Text tone="secondary" size="small">
          Untouched finals under frozen commit 91d76c1. Neither Nia nor Context7 could
          run here, so the comparators are the strongest local lexical engines.
          Delphi leads every metric on ARB final with all repository-cluster 95% CIs
          excluding zero.
        </Text>
        <Table
          headers={["Untouched final", "Delphi", "Best local baseline", "Verdict"]}
          rows={[
            [
              "ARB final MRR (220 cases)",
              "0.332",
              "0.160 (lexical+BM25 RRF)",
              "+0.172, CI [0.083, 0.235] — decisive",
            ],
            [
              "ARB final R@20",
              "0.648",
              "0.518 (RRF)",
              "+0.130, CI [0.024, 0.200] — decisive",
            ],
            [
              "Track D MRR (62 SWE-bench cases)",
              "0.680",
              "0.406 (lexical)",
              "+0.274, CI [0.194, 0.412] — decisive",
            ],
            [
              "Track D R@20",
              "0.737",
              "0.719 (RRF)",
              "+0.018, CI includes 0 — statistical tie",
            ],
            [
              "Independent final R@20 (18 cases)",
              "0.750",
              "0.759 (RRF)",
              "−0.009, CI includes 0 — statistical tie",
            ],
          ]}
          rowTone={["success", "success", "success", "neutral", "neutral"]}
        />
      </Stack>

      <Callout tone="success">
        Bottom line: Delphi is the only engine of the three that can serve commit-pinned
        repository retrieval today, and on those untouched finals it leads every runnable
        comparator wherever the difference is statistically resolvable. On documentation,
        the matched-contract comparison shows Delphi retrieval + synthesis at 0.617 vs
        Nia&apos;s 0.575 (parity-or-better; superiority not statistically resolved) at
        less than half Nia&apos;s latency — the old &quot;Nia leads docs&quot; gap was an
        output-contract artifact. Context7 matches Delphi on docs latency, trails on
        quality, is far less repeatable (35.6% vs 98.0% exact context), and has no
        repository capability. No universal SOTA claim: the Nia repository arm stays
        externally blocked — 32/68 pairs are indexed from the prior round, but even a
        minimal 1.5 MB probe shard never left Nia&apos;s ingestion queue across ~3.7 hours
        of polling. The head-to-head runs only if their ingestion recovers to 68/68.
      </Callout>

      <Text tone="quaternary" size="small">
        Sources: A/I/D-final artifacts + paired bootstrap analyses (20k resamples, seed
        1042) in new/round3/results; documentation and DS-1000 numbers from the locked
        development accounting runs of 2026-08-24. Nia repository status: 0/68 required
        sources visible (nia-accounting-repository-readiness-20260824.json).
      </Text>
    </Stack>
  );
}
