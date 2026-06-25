export function getCurrentSeasonalContext(date: Date = new Date()): any {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const iso = date.toISOString().slice(0, 10);
  if (month === 4 || (month === 5 && day <= 12)) return { season: "Mother's Day", reason: "Mother's Day gift shopping window", urgency: month === 5 ? "high" : "medium", date_context: iso };
  if (month === 5 || (month === 6 && day <= 20)) return { season: "Father's Day", reason: "Father's Day gift shopping window", urgency: "high", date_context: iso };
  if (month === 5 || month === 6) return { season: "graduation", reason: "Graduation gift season", urgency: "medium", date_context: iso };
  if (month >= 6 && month <= 8) return { season: "summer/outdoor", reason: "Summer hobby and travel season", urgency: "medium", date_context: iso };
  if (month === 8 || month === 9) return { season: "back to school", reason: "Teacher/student gift and classroom season", urgency: "medium", date_context: iso };
  if (month === 10) return { season: "fall/Halloween", reason: "Halloween and fall decor season", urgency: "high", date_context: iso };
  if (month === 11 || month === 12) return { season: "Christmas/holiday gifts", reason: "Holiday gift buying season", urgency: "high", date_context: iso };
  return { season: "evergreen gifts", reason: "Evergreen gifting and hobby niches", urgency: "low", date_context: iso };
}

export function scoreOpportunity(combination: any = {}): any {
  let score = 40;
  const reasons: string[] = [];
  const source = combination.source || combination.demandSignal?.source || "local_seed";
  if (source === "etsy_api") score += 20;
  if (source === "everbee_export") score += 18;
  if (source === "local_seed") score += 8;
  if (combination.seasonality?.urgency === "high") score += 15;
  if ((combination.itemLook?.riskLevel || combination.risk) === "low") score += 10;
  score = Math.max(0, Math.min(100, Math.round(score)));
  return { score, grade: score >= 80 ? "A" : score >= 65 ? "B" : score >= 50 ? "C" : "Reject", reasons };
}

export async function researchEtsyTrends(input: any = {}): Promise<any> {
  return {
    ok: true,
    source: "local_seed",
    seasonality: getCurrentSeasonalContext(),
    itemLooks: [],
    productMatches: [],
    recommendedCombinations: [],
    blockedTerms: [],
    warnings: ["TypeScript mirror only; runtime uses etsyMarketResearch.mjs."],
    confidence: 0.5,
    diagnostics: {},
    trends: []
  };
}
