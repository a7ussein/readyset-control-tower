"""What the engine must report for each kind of change. Written before the engine.

Every test builds two tiny releases (tests/tiny_release.py), runs `control_tower.compare(folder_a, folder_b)` and
checks the findings document it returns, which has the shape in docs/OUTPUT-CONTRACT.md.

Until the engine exists these tests are skipped, not failed.
"""
import os
import tempfile
import unittest

from tests.tiny_release import (A1_BEFORE, A2_BEFORE, CLIN_ONLY, CLINICAL, COPY_NUMBER, ER, HISTOLOGY, MET, MUTATION, N1, N2,
                                NEW1, NEW2, NORMAL, P1, P2, P3, PAM50, PROTEIN, RNA, SURVIVAL, U1, TinyRelease)

from control_tower import compare
from control_tower.compare import _severity


def samples(finding):
    return sorted({e["id"] for e in finding["evidence"] if e["kind"] == "sample"})


@unittest.skipIf(compare is None, "the engine (control_tower.compare) does not exist yet")
class Detectors(unittest.TestCase):
    def run_pair(self, change, analyses=None):
        a = TinyRelease()
        b = change(a.copy())
        d = tempfile.mkdtemp()
        self.doc = compare(a.write(os.path.join(d, "A")), b.write(os.path.join(d, "B")), analyses)
        return self.doc

    # ---- 0. the question decides the answer -----------------------------------------------------------
    def test_the_same_swap_is_conditional_for_a1_and_ready_for_a2(self):
        swap = lambda b: b.swap(PROTEIN, P1, N1)
        for_a1 = self.run_pair(swap, ["A1"])
        self.assertEqual((for_a1["verdict"], self.only("sample_swap")["severity"]), ("Conditional", "high"))
        self.assertEqual([a["id"] for a in for_a1["analyses"]], ["A1"])
        for_a2 = self.run_pair(swap, ["A2"])
        f = self.only("sample_swap")                                           # still reported, never hidden
        self.assertEqual((for_a2["verdict"], f["severity"], f["affects_analyses"], f["not_affected_analyses"]),
                         ("Ready", "high", [], ["A2"]))                     # as serious as before; it just does not reach A2
        self.assertEqual([(a["id"], a["status"]) for a in for_a2["analyses"]], [("A2", "not_rerun")])
        self.assertEqual(for_a2["x_readyset"]["unrelated_findings"], 1)
        self.assertIn("A2", for_a2["question"])
        self.assertNotIn("A1", for_a2["question"])

    def test_a_new_question_needs_no_new_code(self):
        her2 = {"id": "Q1", "type": "mean_by_group", "title": "HER2 by ER status", "file": PROTEIN, "row": "HER2",
                "column": ER, "groups": ["Positive", "Negative"]}
        doc = self.run_pair(lambda b: b.set_cell(PROTEIN, "HER2", P1, ""), [her2])     # A1 ignores this cell; Q1 reads it
        self.assertEqual(self.only("missing_data")["affects_analyses"], ["Q1"])
        q1 = self.analysis("Q1")
        self.assertEqual(q1["status"], "changed")
        self.assertIn("mean_positive", q1["before"])
        self.assertEqual(doc["x_readyset"]["analysis_titles"]["Q1"], "HER2 by ER status")
        mix = {"id": "Q2", "type": "category_mix", "column": HISTOLOGY}
        self.run_pair(lambda b: b.set_cell(PROTEIN, "HER2", P1, ""), [mix])
        self.assertEqual((self.doc["verdict"], self.analysis("Q2")["status"]), ("Ready", "not_rerun"))

    def test_a_question_that_cannot_be_built_is_refused(self):
        from control_tower.analyses import BadQuestion
        for bad in (["A9"], [], ["A1", "A1"], [{"id": "Q1", "type": "mean_by_group"}], [{"id": "Q1", "type": "magic"}],
                    [{"id": "A1", "type": "category_mix", "column": ER}]):
            with self.assertRaises(BadQuestion, msg=str(bad)):
                self.run_pair(lambda b: b, bad)

    def test_a_question_about_something_that_is_not_in_the_data_is_refused_not_answered_ready(self):
        from control_tower.analyses import BadQuestion
        base = {"id": "Q1", "type": "mean_by_group", "file": PROTEIN, "row": "HER2", "column": ER, "groups": ["Positive", "Negative"]}
        for wrong, said in ((dict(base, row="NOPE"), "no row called NOPE"), (dict(base, column="nope_col"), "no column called nope_col"),
                            (dict(base, groups=["Positive", "Purple"]), "no sample has the value Purple"),
                            ({"id": "Q2", "type": "category_mix", "column": "nope_col"}, "no column called nope_col")):
            with self.assertRaises(BadQuestion) as e:
                self.run_pair(lambda b: b.swap(PROTEIN, P1, N1), [wrong])
            self.assertIn(said, str(e.exception))

    def test_the_same_folder_twice_is_said_out_loud(self):
        a = TinyRelease()
        folder = a.write(os.path.join(tempfile.mkdtemp(), "A"))
        doc = compare(folder, folder)
        self.assertEqual(doc["verdict"], "Ready")
        self.assertIn("same folder", doc["x_readyset"]["notes"][0])

    def test_each_finding_carries_its_own_effect_not_the_combined_one(self):
        # Two changes reach A1: a swap across ER groups, and one blanked ER-alpha value.
        doc = self.run_pair(lambda b: b.swap(PROTEIN, P1, N1).set_cell(PROTEIN, "ERALPHA", P2, ""))
        swap, blank = self.only("sample_swap"), self.only("missing_data")
        fx = doc["x_readyset"]["effects"]
        alone_swap, alone_blank = fx[swap["id"]]["A1"], fx[blank["id"]]["A1"]
        combined = self.analysis("A1")["after"]
        self.assertEqual(alone_swap["before"], self.analysis("A1")["before"])
        self.assertEqual(alone_swap["after"]["mean_positive"], 0.933)             # the swap alone, as in the swap test
        self.assertNotEqual(alone_swap["after"], combined)                        # the combined result includes the blank too
        self.assertNotEqual(alone_blank["after"], combined)
        self.assertEqual(alone_swap["size"], "large")
        self.assertIn(alone_swap["measure"], alone_swap["after"])

    def test_a_fix_is_sized_to_what_its_finding_does(self):
        doc = self.run_pair(lambda b: b.swap(PROTEIN, P1, N1).swap(COPY_NUMBER, P1, N1))
        level = {r["addresses"][0]: doc["x_readyset"]["repair_priority"][r["id"]]["level"] for r in doc["repairs"]}
        by_file = {f["evidence"][0]["file"]: f["id"] for f in doc["findings"]}
        self.assertEqual(level[by_file[PROTEIN]], "before use")                   # it moves A1
        self.assertEqual(level[by_file[COPY_NUMBER]], "for the record")           # nothing in the question reads it
        same = self.run_pair(lambda b: b.swap(PROTEIN, P1, P2))                   # both ER positive: A1 holds
        fix = same["x_readyset"]["repair_priority"][same["repairs"][0]["id"]]
        self.assertEqual(fix["level"], "before use")                              # wrong identities are never "when convenient"
        self.assertIn("another sample's data", fix["why"])
        gone = self.run_pair(lambda b: b.drop_row(PROTEIN, "ERALPHA"))            # A1 cannot run at all
        why = [gone["x_readyset"]["repair_priority"][r["id"]]["why"] for r in gone["repairs"]]
        self.assertTrue(all("moves a result" not in w for w in why))

    def test_the_folders_the_wrong_way_round_get_a_hint_not_a_crash(self):
        d = tempfile.mkdtemp()
        a = TinyRelease()
        trusted = a.write(os.path.join(d, "trusted"))
        altered = a.copy().swap(PROTEIN, P1, N1).write(os.path.join(d, "altered"))
        with open(os.path.join(altered, "CHANGES.json"), "w") as fh:
            fh.write("{}")
        doc = compare(altered, trusted)
        self.assertIn("wrong way round", doc["x_readyset"]["notes"][0])
        self.assertEqual(compare(trusted, altered)["x_readyset"]["notes"], [])

    def test_only_headline_numbers_make_an_effect_large(self):
        from control_tower.compare import _size
        base = {"n_samples": 100, "n_positive": 60, "n_negative": 40, "mean_positive": 2.0, "mean_negative": -1.0, "difference": 3.0}
        self.assertEqual(_size(base, dict(base, n_samples=103, n_positive=63))[0], "small")       # only counts moved
        self.assertEqual(_size(base, dict(base, difference=3.004))[0], "small")                    # 0.13 percent
        self.assertEqual(_size(base, dict(base, difference=3.05))[:2], ("large", "difference"))    # 1.7 percent
        self.assertEqual(_size(base, dict(base))[0], "none")

    def test_a_meaningless_category_question_is_refused(self):
        from control_tower.analyses import BadQuestion, CategoryMix
        self.assertIsNone(CategoryMix("Q", "mix", HISTOLOGY).problem(TinyRelease().write(os.path.join(tempfile.mkdtemp(), "A"))))
        with self.assertRaises(BadQuestion):
            self.run_pair(lambda b: b, [{"id": "Q1", "type": "category_mix", "column": "no_such_column"}])

    def test_severity_goes_by_the_kind_of_problem_and_never_by_the_question(self):
        self.assertEqual([_severity(k, False) for k in ("sample_swap", "duplicate", "membership_change", "label_conflict", "other")],
                         ["high", "high", "medium", "medium", "medium"])
        self.assertEqual([_severity(k, True) for k in ("label_conflict", "missing_data", "other", "membership_change")],
                         ["high", "high", "high", "medium"])
        for file in (COPY_NUMBER, MUTATION):                                      # a swap nobody reads is still a swap
            self.run_pair(lambda b: b.swap(file, P1, N1))
            self.assertEqual((self.only("sample_swap")["severity"], self.doc["verdict"]), ("high", "Ready"))
        relabel = lambda b: b.relabel(ER, P1, "Negative")
        both = self.run_pair(relabel)["findings"][0]["severity"]
        only_a2 = self.run_pair(relabel, ["A2"])["findings"][0]["severity"]
        self.assertEqual((both, only_a2), ("high", "high"))                       # the same finding, whatever is asked
        unread = self.run_pair(lambda b: b.relabel(HISTOLOGY, P1, "Other"))
        self.assertEqual(unread["findings"][0]["severity"], "medium")

    def test_every_finding_says_which_rule_found_it_and_why_it_matters(self):
        doc = self.run_pair(lambda b: b.swap(PROTEIN, P1, N1))
        rule = doc["x_readyset"]["rules"][self.only("sample_swap")["id"]]
        self.assertIn("fingerprint", rule["detected_by"])
        self.assertTrue(any(line.startswith("A1 is touched") for line in rule["impact"]))
        self.assertTrue(any(line.startswith("A2 is not touched") for line in rule["impact"]))
        self.assertTrue(rule["severity"].startswith("High"))

    def kinds(self):
        return sorted(f["kind"] for f in self.doc["findings"])

    def only(self, kind):
        found = [f for f in self.doc["findings"] if f["kind"] == kind]
        self.assertEqual(len(found), 1, f"expected exactly one {kind} finding, got {self.kinds()}")
        return found[0]

    def analysis(self, name):
        return next(a for a in self.doc["analyses"] if a["id"] == name)

    def files(self):
        return {f["file"]: f for f in self.doc["x_readyset"]["files"]}

    # ---- 1. nothing changed -------------------------------------------------------------------------
    def test_identical_releases_are_ready_and_no_file_is_opened(self):
        doc = self.run_pair(lambda b: b)
        self.assertEqual((doc["findings"], doc["verdict"]), ([], "Ready"))
        self.assertTrue(all(f["status"] == "unchanged" and not f["opened"] for f in self.files().values()))
        self.assertEqual([a["status"] for a in doc["analyses"]], ["not_rerun", "not_rerun"])

    def test_columns_in_a_different_order_is_not_a_change_to_any_sample(self):
        doc = self.run_pair(lambda b: b.reorder_columns(PROTEIN))
        self.assertEqual(doc["findings"], [])
        self.assertEqual(self.files()[PROTEIN]["status"], "changed")           # the bytes differ; no sample does
        self.assertIn("every value is the same", self.files()[PROTEIN]["note"])

    def test_a_file_with_findings_carries_no_same_values_note(self):
        self.run_pair(lambda b: b.swap(PROTEIN, P1, N1))
        self.assertNotIn("note", self.files()[PROTEIN])

    def test_a_swap_comes_with_the_two_values_a_reader_can_check_by_hand(self):
        doc = self.run_pair(lambda b: b.swap(PROTEIN, P1, N1))
        w = doc["x_readyset"]["witness"][self.only("sample_swap")["id"]]
        self.assertEqual((w["file"], w["row"]), (PROTEIN, "ERALPHA"))
        v = {x["sample"]: (x["before"], x["after"]) for x in w["values"]}
        self.assertEqual(v[P1][0], v[N1][1])                                   # each now holds the other's value
        self.assertEqual(v[N1][0], v[P1][1])
        self.assertNotEqual(v[P1][0], v[P1][1])

    # ---- 2. swap ------------------------------------------------------------------------------------
    def test_a_swap_across_er_groups_names_both_samples_and_changes_a1(self):
        self.run_pair(lambda b: b.swap(PROTEIN, P1, N1))
        f = self.only("sample_swap")
        self.assertEqual(samples(f), sorted([P1, N1]))
        self.assertEqual((f["affects_analyses"], f["not_affected_analyses"], f["severity"]), (["A1"], ["A2"], "high"))
        a1 = self.analysis("A1")
        self.assertEqual(a1["status"], "changed")
        for k, v in A1_BEFORE.items():
            self.assertEqual(a1["before"][k], v, k)
        self.assertEqual(a1["after"]["mean_positive"], 0.933)                  # (-1.0 + 2.0 + 1.8) / 3
        self.assertEqual(a1["after"]["mean_negative"], 0.7)                    # (2.2 - 0.8) / 2
        self.assertEqual(self.analysis("A2")["status"], "not_rerun")
        self.assertEqual(self.doc["verdict"], "Conditional")
        self.assertEqual(self.kinds(), ["sample_swap"])                        # nothing else is reported for it

    def test_a_swap_inside_one_er_group_reruns_a1_and_finds_it_unchanged(self):
        self.run_pair(lambda b: b.swap(PROTEIN, P1, P2))
        f = self.only("sample_swap")
        self.assertEqual((f["affects_analyses"], f["severity"]), (["A1"], "high"))      # a swap is high even when the result holds
        a1 = self.analysis("A1")
        self.assertEqual(a1["status"], "unchanged")
        self.assertEqual(a1["before"], a1["after"])

    def test_a_swap_in_a_file_no_analysis_reads_affects_neither(self):
        self.run_pair(lambda b: b.swap(COPY_NUMBER, P1, N1))
        f = self.only("sample_swap")
        self.assertEqual((f["affects_analyses"], f["not_affected_analyses"]), ([], ["A1", "A2"]))
        self.assertEqual(f["severity"], _severity(f["kind"], False))
        self.assertEqual([a["status"] for a in self.doc["analyses"]], ["not_rerun", "not_rerun"])
        self.assertFalse(self.files()[RNA]["opened"])

    def test_a_swap_between_samples_a1_does_not_use_does_not_affect_it(self):
        self.run_pair(lambda b: b.swap(PROTEIN, MET, U1))                      # a metastasis and a tumour with no ER status
        self.assertEqual(self.only("sample_swap")["affects_analyses"], [])

    def test_three_samples_rotated_is_one_finding_naming_all_three(self):
        def rotate(b):
            t = b.by_col[PROTEIN][2]
            t[P1], t[P2], t[N1] = t[P2], t[N1], t[P1]
            return b
        self.run_pair(rotate)
        self.assertEqual(samples(self.only("sample_swap")), sorted([P1, P2, N1]))

    # ---- 3. duplicate and membership ----------------------------------------------------------------
    def test_a_copied_sample_under_a_new_id_with_another_removed(self):
        self.run_pair(lambda b: b.copy_as(PROTEIN, P1, NEW1, replacing=N2))    # same count as before
        dup = self.only("duplicate")
        self.assertEqual(samples(dup), [NEW1])                                 # the copy; its source is named in the note
        self.assertIn(P1, dup["evidence"][0]["note"])
        mem = self.only("membership_change")
        self.assertEqual(samples(mem), [N2])                                   # who left; the arrival is the copy above
        self.assertIn("Basal 1", mem["summary"])                               # which subgroup lost coverage
        # The new id has no clinical record, so A1 never reads the copy. What moves A1 is the sample that left.
        self.assertEqual((dup["affects_analyses"], mem["affects_analyses"]), ([], ["A1"]))
        self.assertEqual(self.analysis("A1")["status"], "changed")
        self.assertEqual(mem["severity"], "medium")        # lost coverage is never rated high, even when the result moves
        self.assertEqual(self.analysis("A1")["after"]["n_negative"], 1)

    def test_a_copy_landing_on_an_id_that_has_a_clinical_record_does_affect_a1(self):
        self.run_pair(lambda b: b.copy_as(PROTEIN, N1, CLIN_ONLY))             # an ER-positive id now carries an ER-negative profile
        dup = self.only("duplicate")
        self.assertEqual(samples(dup), [CLIN_ONLY])
        self.assertEqual((dup["affects_analyses"], dup["severity"]), (["A1"], "high"))
        a1 = self.analysis("A1")
        self.assertEqual((a1["status"], a1["after"]["n_positive"]), ("changed", 4))

    def test_one_edited_cell_that_happens_to_match_another_sample_is_not_a_copy(self):
        self.run_pair(lambda b: b.set_cell(MUTATION, "TP53", P1, "1"))         # P1 now equals P3 in this tiny file
        self.assertEqual(self.kinds(), ["other"])

    def test_an_existing_sample_overwritten_with_another_samples_values_is_a_copy(self):
        def overwrite(b):
            b.by_col[PROTEIN][2][P2] = list(b.by_col[PROTEIN][2][N1])
            return b
        self.run_pair(overwrite)
        dup = self.only("duplicate")
        self.assertEqual((samples(dup), dup["affects_analyses"]), ([P2], ["A1"]))

    def test_samples_that_were_already_identical_are_not_called_duplicates(self):
        doc = self.run_pair(lambda b: b.relabel("OS.time", N1, "301", file=SURVIVAL))
        self.assertNotIn("duplicate", self.kinds())                            # P1 and its normal share a survival row in both releases
        self.assertEqual(self.files()[SURVIVAL]["status"], "changed")

    def test_twins_that_change_together_are_not_copies(self):
        # P1 and its normal tissue share one survival record. When that record is updated, both rows change the same way.
        self.run_pair(lambda b: b.relabel("OS.time", P1, "1300", file=SURVIVAL).relabel("OS.time", NORMAL, "1300", file=SURVIVAL))
        self.assertEqual(self.kinds(), ["other"])
        self.assertEqual(samples(self.only("other")), sorted([P1, NORMAL]))

    def test_a_sample_that_only_left_is_a_membership_change(self):
        self.run_pair(lambda b: b.remove(PROTEIN, P3))
        self.assertEqual(samples(self.only("membership_change")), [P3])
        self.assertEqual(self.kinds(), ["membership_change"])

    def test_a_renamed_sample_is_one_membership_finding_not_a_duplicate(self):
        self.run_pair(lambda b: b.rename(PROTEIN, P3, NEW2))
        self.assertEqual(samples(self.only("membership_change")), sorted([P3, NEW2]))
        self.assertEqual(self.kinds(), ["membership_change"])

    def test_a_normal_tissue_row_leaving_the_clinical_file_affects_neither(self):
        self.run_pair(lambda b: b.remove(CLINICAL, NORMAL))
        self.assertEqual(self.only("membership_change")["affects_analyses"], [])

    # ---- 4. relabel ---------------------------------------------------------------------------------
    def test_er_status_relabelled_affects_a1_only(self):
        self.run_pair(lambda b: b.relabel(ER, P1, "Negative").relabel(ER, P2, "Negative"))
        f = self.only("label_conflict")
        self.assertEqual(samples(f), sorted([P1, P2]))                         # one finding for the column, both samples
        self.assertEqual((f["affects_analyses"], f["not_affected_analyses"]), (["A1"], ["A2"]))
        self.assertEqual(self.analysis("A1")["after"]["n_positive"], 1)
        self.assertEqual(self.analysis("A2")["status"], "not_rerun")

    def test_rna_subtype_relabelled_affects_a2_only(self):
        self.run_pair(lambda b: b.relabel(PAM50, N1, "LumA"))
        f = self.only("label_conflict")
        self.assertEqual((f["affects_analyses"], f["not_affected_analyses"]), (["A2"], ["A1"]))
        a2 = self.analysis("A2")
        self.assertEqual(a2["status"], "changed")
        self.assertEqual(a2["before"]["counts"], A2_BEFORE["counts"])
        self.assertEqual(a2["after"]["counts"], {"Basal": 1, "Her2": 1, "LumA": 4})
        self.assertEqual(self.analysis("A1")["status"], "not_rerun")

    def test_a_column_neither_analysis_reads_affects_neither(self):
        self.run_pair(lambda b: b.relabel(HISTOLOGY, P1, "Lobular"))
        f = self.only("label_conflict")
        self.assertEqual((f["affects_analyses"], f["not_affected_analyses"]), ([], ["A1", "A2"]))
        self.assertEqual(f["severity"], _severity(f["kind"], False))

    def test_er_status_relabelled_for_a_sample_with_no_protein_data_does_not_affect_a1(self):
        self.run_pair(lambda b: b.relabel(ER, NORMAL, "Negative"))             # the normal is not in the protein file
        self.assertEqual(self.only("label_conflict")["affects_analyses"], [])

    # ---- 5. missing data and the catch-all ----------------------------------------------------------
    def test_a_value_that_became_blank_is_missing_data(self):
        self.run_pair(lambda b: b.set_cell(PROTEIN, "ERALPHA", P1, ""))
        f = self.only("missing_data")
        self.assertEqual((samples(f), f["affects_analyses"]), ([P1], ["A1"]))
        self.assertTrue(any(e["kind"] == "protein" and e["id"] == "ERALPHA" for e in f["evidence"]))

    def test_a_blanked_cell_in_a_row_a1_does_not_read_does_not_affect_it(self):
        self.run_pair(lambda b: b.set_cell(PROTEIN, "HER2", P1, ""))
        self.assertEqual(self.only("missing_data")["affects_analyses"], [])

    def test_a_changed_value_no_detector_explains_is_reported_not_dropped(self):
        self.run_pair(lambda b: b.set_cell(MUTATION, "TP53", P1, "1"))
        f = self.only("other")
        self.assertEqual((samples(f), f["confidence"], f["needs_human_review"]), ([P1], "low", True))

    def test_when_too_many_cells_differ_the_samples_are_reported_as_a_group_not_dropped(self):
        from control_tower import detect
        saved, detect.MAX_CELLS = detect.MAX_CELLS, 2
        try:
            self.run_pair(lambda b: b.set_cell(MUTATION, "TP53", P1, "1").set_cell(MUTATION, "GATA3", P1, "1")
                          .set_cell(MUTATION, "TP53", N1, "0").set_cell(MUTATION, "PIK3CA", N2, "0"))
        finally:
            detect.MAX_CELLS = saved
        f = self.only("other")
        self.assertEqual(samples(f), sorted([P1, N1, N2]))                     # every changed sample is still named
        self.assertIn("too many to list", f["summary"])
        self.assertEqual((f["confidence"], f["needs_human_review"]), ("low", True))

    def test_a_relabel_of_every_sample_is_still_a_relabel(self):
        def everyone(b):
            for s in list(b.by_row[CLINICAL][2]):
                b.relabel(HISTOLOGY, s, "Recoded")
            return b
        self.run_pair(everyone)
        f = self.only("label_conflict")
        self.assertEqual(len(samples(f)), 9)
        self.assertEqual(f["affects_analyses"], [])

    # ---- 6. structure -------------------------------------------------------------------------------
    def test_a_file_missing_from_the_new_release_is_insufficient_evidence(self):
        doc = self.run_pair(lambda b: b.without_file(PROTEIN))
        self.assertEqual(doc["verdict"], "Insufficient Evidence")
        self.assertTrue(any(e["kind"] == "file" and e["id"] == PROTEIN for f in doc["findings"] for e in f["evidence"]))

    def test_the_rna_file_missing_from_both_releases_is_fine(self):
        a, b = TinyRelease().without_file(RNA), TinyRelease().without_file(RNA)
        d = tempfile.mkdtemp()
        doc = compare(a.write(os.path.join(d, "A")), b.write(os.path.join(d, "B")))
        self.assertEqual((doc["findings"], doc["verdict"]), ([], "Ready"))

    def test_the_row_a1_needs_being_gone_blocks(self):
        doc = self.run_pair(lambda b: b.drop_row(PROTEIN, "ERALPHA"))
        self.assertEqual(doc["verdict"], "Blocked")
        self.assertIn("A1", [a for f in doc["findings"] for a in f["affects_analyses"]])

    # ---- 7. several at once, and the rules every output obeys ---------------------------------------
    def test_three_changes_at_once_are_three_separate_findings(self):
        self.run_pair(lambda b: b.swap(PROTEIN, P1, N1).relabel(PAM50, N2, "LumA").set_cell(MUTATION, "TP53", P2, "1"))
        self.assertEqual(self.kinds(), ["label_conflict", "other", "sample_swap"])
        self.assertEqual([a["status"] for a in self.doc["analyses"]], ["changed", "changed"])

    def test_every_finding_obeys_the_contract(self):
        self.run_pair(lambda b: b.swap(PROTEIN, P1, N1).copy_as(PROTEIN, P2, NEW1, replacing=N2).relabel(HISTOLOGY, P3, "Ductal"))
        doc = self.doc
        self.assertEqual(doc["format_version"], "0.2")
        self.assertEqual(doc["producer"], {"team": "Automyte", "product": "Cohort Control Tower", "track": "cohort-firewall"})
        self.assertEqual([len(r["files"]) for r in doc["data"]["releases"]], [6, 6])
        self.assertTrue(all(f["hash_of"] == "content" for r in doc["data"]["releases"] for f in r["files"]))
        ids = {f["id"] for f in doc["findings"]}
        for f in doc["findings"]:
            self.assertEqual(sorted(f["affects_analyses"] + f["not_affected_analyses"]), ["A1", "A2"], f["id"])
            self.assertTrue(f["limitation"] and isinstance(f["needs_human_review"], bool), f["id"])
            self.assertTrue(all(len(s) == 15 for s in samples(f)), f["id"])
        for r in doc.get("repairs", []):
            self.assertTrue(r["addresses"] and set(r["addresses"]) <= ids, r["id"])     # never an unsupported repair


if __name__ == "__main__":
    unittest.main()
