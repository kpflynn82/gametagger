import type { components } from "./api-schema";
export type Capabilities = components["schemas"]["Capabilities"];
export type Project = components["schemas"]["ProjectView"];
export type ProjectInput = components["schemas"]["ProjectCreate"];
export type Run = components["schemas"]["RunView"];
export type Catalog = components["schemas"]["CatalogPage"];
export type Review = components["schemas"]["ReviewCreate"];
export type Tag = components["schemas"]["TagView"];
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "X-GameTagger-Request": "1",
      ...(typeof options.body === "string"
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const value = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : "Check the supplied fields.",
    );
  }
  return response.json();
}
export type Genre = {
  id: string;
  display_name: string;
  family: string;
  definition: string;
  inclusion_criteria: string[];
  exclusion_notes: string[];
};
export type Taxonomy = {
  version: string;
  families: {
    id: string;
    display_name: string;
    definition: string;
    genres: Genre[];
  }[];
  tags: {
    id: string;
    label: string;
    category: string;
    definition: string;
    allowed_evidence: string[];
  }[];
};
export const words = (s: string) => s.replaceAll("_", " ");
