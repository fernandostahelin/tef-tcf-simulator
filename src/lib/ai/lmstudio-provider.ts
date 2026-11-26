import { SCORING_SCHEMA } from "./schema";
import type { ScoringProvider } from "./types";

const DEFAULT_BASE_URL = "http://localhost:1234/v1";

export type LmStudioProviderOptions = {
  baseUrl?: string;
  modelId?: string;
  fetchImpl?: typeof fetch;
};

export function createLmStudioProvider(options: LmStudioProviderOptions = {}): ScoringProvider {
  const baseUrl = (options.baseUrl ?? process.env.LMSTUDIO_BASE_URL ?? DEFAULT_BASE_URL).replace(
    /\/+$/,
    "",
  );
  const modelId = options.modelId ?? process.env.LMSTUDIO_SCORING_MODEL ?? "";
  const fetchImpl = options.fetchImpl ?? fetch;

  return {
    id: "lmstudio",
    modelId,
    async score(system, userContent) {
      if (!modelId) {
        throw new Error(
          "LMSTUDIO_SCORING_MODEL manquant — indiquez l'identifiant du modèle chargé dans LM Studio (lms ls).",
        );
      }

      let response: Response;
      try {
        response = await fetchImpl(`${baseUrl}/chat/completions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: modelId,
            temperature: 0,
            max_tokens: 2048,
            messages: [
              { role: "system", content: system },
              { role: "user", content: userContent },
            ],
            response_format: {
              type: "json_schema",
              json_schema: {
                name: "scoring_result",
                strict: true,
                schema: SCORING_SCHEMA,
              },
            },
          }),
        });
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        throw new Error(
          `Impossible de joindre LM Studio à ${baseUrl} — lancez le serveur local (lms server start) et chargez le modèle "${modelId}". ${detail}`,
        );
      }

      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        throw new Error(
          `Erreur du serveur LM Studio (${response.status}) à ${baseUrl} — vérifiez que le serveur est lancé et que le modèle "${modelId}" est chargé (lms load ${modelId}). ${detail}`,
        );
      }

      const data = (await response.json()) as {
        choices?: Array<{
          message?: { content?: string | null; reasoning_content?: string | null };
        }>;
      };
      const message = data.choices?.[0]?.message;
      const text = message?.content?.trim() || message?.reasoning_content?.trim();
      if (!text) {
        throw new Error("Aucune réponse de correction reçue (LM Studio).");
      }
      return text;
    },
  };
}

export const lmstudioProvider = createLmStudioProvider();
