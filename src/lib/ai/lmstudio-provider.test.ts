import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SCORING_SCHEMA } from "./schema";
import { createLmStudioProvider } from "./lmstudio-provider";

const scoringJson = JSON.stringify({
  linguistic: 6,
  pragmatic: 7,
  sociolinguistic: 5,
  estimatedNclc: 7,
  confidence: "medium",
  feedbackText: "Texte clair, avec quelques accords à revoir.",
  strengthsHighlighted: ["message compréhensible"],
  improvementAreas: ["accords"],
});

function providerWith(fetchImpl: typeof fetch, modelId = "qwen3-30b-a3b-instruct-2507-mlx") {
  return createLmStudioProvider({
    baseUrl: "http://127.0.0.1:1234/v1/",
    modelId,
    fetchImpl,
  });
}

describe("LM Studio scoring provider", () => {
  it("posts the shared rubric to the local chat completions API and returns the JSON text", async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      calls.push({
        url: String(input),
        body: JSON.parse(String(init?.body)),
      });
      return new Response(
        JSON.stringify({ choices: [{ message: { content: scoringJson } }] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    const provider = providerWith(fetchImpl);
    const text = await provider.score("rubrique", "réponse du candidat");

    assert.equal(provider.id, "lmstudio");
    assert.equal(provider.modelId, "qwen3-30b-a3b-instruct-2507-mlx");
    assert.equal(text, scoringJson);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:1234/v1/chat/completions");
    assert.deepEqual(calls[0].body, {
      model: "qwen3-30b-a3b-instruct-2507-mlx",
      temperature: 0,
      max_tokens: 2048,
      messages: [
        { role: "system", content: "rubrique" },
        { role: "user", content: "réponse du candidat" },
      ],
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "scoring_result",
          strict: true,
          schema: SCORING_SCHEMA,
        },
      },
    });
  });

  it("tells the learner to start the local server when LM Studio is unreachable", async () => {
    const fetchImpl: typeof fetch = async () => {
      throw new TypeError("fetch failed");
    };
    const provider = providerWith(fetchImpl, "local-model");

    await assert.rejects(() => provider.score("rubrique", "texte"), /lms server start/);
  });

  it("tells the learner to load the model when LM Studio rejects the request", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response("model not loaded", { status: 400 });
    const provider = providerWith(fetchImpl, "local-model");

    await assert.rejects(() => provider.score("rubrique", "texte"), /lms load local-model/);
  });

  it("refuses to score when no model id is configured", async () => {
    let called = false;
    const fetchImpl: typeof fetch = async () => {
      called = true;
      throw new Error("should not fetch");
    };
    const provider = providerWith(fetchImpl, "");

    await assert.rejects(() => provider.score("rubrique", "texte"), /LMSTUDIO_SCORING_MODEL/);
    assert.equal(called, false);
  });

  it("reads reasoning_content when a reasoning model leaves the message empty", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          choices: [{ message: { content: "", reasoning_content: scoringJson } }],
        }),
        { status: 200 },
      );
    const provider = providerWith(fetchImpl);

    assert.equal(await provider.score("rubrique", "texte"), scoringJson);
  });

  it("rejects an empty completion", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ choices: [{ message: { content: "" } }] }), {
        status: 200,
      });
    const provider = providerWith(fetchImpl);

    await assert.rejects(
      () => provider.score("rubrique", "texte"),
      /Aucune réponse de correction reçue \(LM Studio\)/,
    );
  });
});
