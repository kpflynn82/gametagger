// Illustrative mathematical UI fixture, never a benchmark or human annotation.
import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it } from "vitest";
import { QualityView, type Quality } from "../src/quality";
const m = (n: number, d: number) => ({ numerator: n, denominator: d, value: d ? n/d : null });
function fixture(): Quality {
  const baseline = { records:100, human_supported_labels:100, errors:1, not_evaluated:99,
    accepted_precision:m(0,0), accepted_only_recall:m(0,0), end_to_end_positive_recovery:m(0,100),
    game_truth_positive_recovery:m(0,100), four_state_brier_sum_over_classes:m(0,0), calibration:[] };
  return { available:true, reason:null, target:"Illustrative / UI test data", paired_games:100, assigned_games:100,
    tags:[{ id:"mechanic_parry", label:"Parry mechanic", category:"combat", warning:"Synthetic mathematical fixture only",
      baseline, candidate:{...baseline, errors:0, accepted_precision:m(1,1), accepted_only_recall:m(1,1),
        end_to_end_positive_recovery:m(1,100)}, precision_change_pp:null, recall_change_pp:1 }] };
}
it("renders accepted precision beside end-to-end recall and never invents a missing precision", () => {
  render(<QualityView quality={fixture()} />);
  expect(screen.getByText(/100 paired reviewed games/)).toBeInTheDocument();
  expect(screen.getAllByText("Not measured (n=0)").length).toBeGreaterThan(0);
  expect(screen.getByText("100.00% (1.00 / 1)")).toBeInTheDocument();
  expect(screen.getByText("1.00% (1.00 / 100)")).toBeInTheDocument();
  expect(screen.getByText(/Errors: 1 \/ 100/)).toBeInTheDocument();
  expect(screen.getAllByText(/Plot deferred/)).toHaveLength(2);
  fireEvent.change(screen.getByLabelText("Attribute detail"), {target:{value:"mechanic_parry"}});
  expect(screen.getByText(/Synthetic mathematical fixture only/)).toBeInTheDocument();
});
it("keeps incompatible and empty reports unavailable", () => {
  render(<QualityView quality={{...fixture(),available:false,reason:"Mismatched evidence"}} />);
  expect(screen.getByText("Mismatched evidence")).toBeInTheDocument();
  expect(screen.queryByText("100.00%")).not.toBeInTheDocument();
});
it("provides keyboard-labelled reliability points and a table instead of a sparse curve", () => {
  const q=fixture();
  q.tags[0].baseline.calibration=[{ lower:.5,upper:.6,count:5,mean_selected_probability:m(2.75,5),empirical_correctness:m(3,5) },
    { lower:.8,upper:.9,count:5,mean_selected_probability:m(4.25,5),empirical_correctness:m(4,5) }];
  render(<QualityView quality={q} />);
  expect(screen.getByRole("img",{name:/baseline reliability/})).toBeInTheDocument();
  const point=screen.getByRole("img",{name:/Bucket 0.5 to 0.6/});
  expect(point).toHaveAttribute("tabindex","0");
  expect(screen.getByText("baseline reliability buckets · evidence-supported target")).toBeInTheDocument();
});
