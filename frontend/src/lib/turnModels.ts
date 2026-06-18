import type { ConversationRound } from "./groupRounds";

/** Map completed task models onto rounds that have a final reply (one model per completed turn). */
export function attachTurnModels(
  rounds: ConversationRound[],
  turnModels: string[],
): ConversationRound[] {
  let ci = 0;
  let lastModel: string | null = null;

  return rounds.map((round) => {
    if (round.human) {
      let model: string | null = null;
      if (round.final) {
        model = turnModels[ci] ?? null;
        ci += 1;
      }
      if (model) {
        lastModel = model;
      }
      return { ...round, model };
    }
    if (round.continuedFromCompaction) {
      return { ...round, model: lastModel };
    }
    return { ...round, model: lastModel };
  });
}
