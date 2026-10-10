export const queryKeys = {
  systemStatus: ["system", "status"] as const,
  campaigns: ["campaigns"] as const,
  campaign: (id: string) => ["campaigns", id] as const,
};
