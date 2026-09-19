import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogPage, ResultPage } from "../src/pages";
import { Experiments, Pipeline } from "../src/experiments";
import { api } from "../src/api";
vi.mock("../src/api", async (original) => ({
  ...(await original<typeof import("../src/api")>()),
  api: vi.fn(),
}));
const mocked = vi.mocked(api);
beforeEach(() => {
  mocked.mockReset();
});
const tax = { version: "4.1", families: [], tags: [] };
function mount(node: React.ReactNode, path = "/") {
  return render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);
}
describe("workspace contracts", () => {
  it("shows loading, then a real empty catalog; filters are part of the request", async () => {
    mocked.mockImplementation(async (path) =>
      path === "/taxonomy"
        ? tax
        : path === "/runs"
          ? []
          : { items: [], total: 0, page: 1, page_size: 12 },
    );
    mount(<CatalogPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading catalog");
    await screen.findByText("No projects match");
    fireEvent.change(screen.getByLabelText("Platform"), {
      target: { value: "mobile" },
    });
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith("/projects?platform=mobile&page=1"),
    );
    fireEvent.change(screen.getByLabelText("Search catalog"), {
      target: { value: "test" },
    });
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        "/projects?platform=mobile&page=1&q=test",
      ),
    );
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
  it("preserves pagination and primary-first catalog metadata", async () => {
    mocked.mockImplementation(async (path) =>
      path === "/taxonomy"
        ? tax
        : path.startsWith("/runs")
          ? []
          : {
              items: [
                {
                  id: "p",
                  title: "Illustrative UI fixture",
                  release: "test",
                  platform: "mobile",
                  approved_primary: "puzzle",
                  approved_primary_label: "Puzzle",
                  run_count: 0,
                },
              ],
              total: 13,
              page: 1,
              page_size: 12,
            },
    );
    mount(<CatalogPage />);
    await screen.findByText("Puzzle");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith("/projects?page=2"),
    );
    expect(
      screen.getByRole("columnheader", { name: "Primary genre" }),
    ).toBeInTheDocument();
  });
  it("renders errors as errors rather than fabricated rows", async () => {
    mocked.mockRejectedValue(new Error("Workspace unavailable"));
    mount(<CatalogPage />);
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Workspace unavailable",
    );
    expect(screen.queryByText("No projects match")).not.toBeInTheDocument();
  });
  it("separates incomplete execution from semantic unknown and primary approval", async () => {
    mocked.mockResolvedValue({
      id: "r",
      project_id: "p",
      title: "Illustrative UI test data",
      release: "test",
      platform: "pc",
      mode: "offline",
      status: "partial",
      identity_status: "associated_project",
      primary_genre: null,
      primary_label: null,
      primary_status: "No primary assigned",
      blocker: "Live disabled",
      tags: [
        {
          id: "t",
          label: "Test attribute",
          category: "combat",
          state: null,
          execution: "not_evaluated",
        },
      ],
      assets: [],
      events: [],
      reviews: [],
      observations: [],
      provenance: {},
    });
    mount(
      <Routes>
        <Route path="/runs/:id" element={<ResultPage />} />
      </Routes>,
      "/runs/r",
    );
    await screen.findByText("Not classified");
    expect(screen.getByText("not evaluated")).toBeInTheDocument();
    expect(screen.queryByText("insufficient evidence")).not.toBeInTheDocument();
    expect(screen.getByText("Offline · no recognition")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute(
      "href",
      "/api/runs/r/export?format=json",
    );
  });
  it("leaves an unmeasured comparison undefined with no effect size", async () => {
    mocked.mockResolvedValue({
      recommendation: "Inconclusive",
      reason: "No matched comparison",
      scorecard: [
        {
          metric: "Actual primary correctness",
          baseline: null,
          candidate: null,
          change: null,
          paired_n: 0,
          status: "Not measured",
        },
      ],
      historical: {
        records: 100,
        new_outcomes_all_tags: {},
        per_tag: {},
        text_bearing_abstentions: [],
      },
      case_ledger: [],
      provenance: {},
      clean_pilot: { cases: [] },
    });
    mount(<Experiments />);
    await screen.findByText("Inconclusive");
    expect(screen.getAllByText("Not measured").length).toBeGreaterThan(1);
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Cohort"), {
      target: { value: "mobile" },
    });
    expect(screen.getByText("0 matched cases")).toBeInTheDocument();
  });
  it("makes both implemented-flow diagrams keyboard selectable", () => {
    mount(<Pipeline shared />);
    const choice = screen.getByRole("button", {
      name: "Conventional classifier",
    });
    fireEvent.click(choice);
    expect(choice).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getAllByText(/same saved observations/i).length,
    ).toBeGreaterThan(0);
  });
});
