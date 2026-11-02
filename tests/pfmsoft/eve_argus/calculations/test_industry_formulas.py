"""Tests for the app-agnostic industry formula reference module.

Expected values marked "in-game" were quoted from the EVE client on 2026-10-27 and
recorded in dev/prompts/Industry-calculations.md.
"""

import pytest

from pfmsoft.eve_argus.calculations import industry_formulas as f

NANO_PUMP_EIV = 2_874_145.02
NANO_PUMP_BASE_STEP_SECONDS = 1575


class TestResearchLevelMultiplier:
    def test_full_range_matches_cumulative_rank_one_seconds(self) -> None:
        """0 to 10 equals the cumulative rank-one seconds over 105."""
        assert f.research_level_multiplier(
            start_level=0, target_level=10
        ) == pytest.approx(256_000 / 105)

    def test_partial_range_uses_cumulative_difference(self) -> None:
        """A partial range uses the difference of cumulative seconds."""
        assert f.research_level_multiplier(
            start_level=4, target_level=6
        ) == pytest.approx((8000 - 1414) / 105)

    def test_first_step_is_one(self) -> None:
        """The first step multiplier is exactly one."""
        assert f.research_level_multiplier(start_level=0, target_level=1) == 1

    def test_same_level_is_zero(self) -> None:
        """An empty range has a zero multiplier."""
        assert f.research_level_multiplier(start_level=3, target_level=3) == 0

    @pytest.mark.parametrize(("start", "target"), [(-1, 1), (0, 11), (5, 4), (11, 11)])
    def test_invalid_levels_raise(self, start: int, target: int) -> None:
        """Out-of-range or descending levels raise ValueError."""
        with pytest.raises(ValueError):
            f.research_level_multiplier(start_level=start, target_level=target)


class TestResearchPercent:
    def test_me_and_te_percent(self) -> None:
        """ME gains 1% and TE gains 2% per level."""
        assert f.material_efficiency_percent(level=10) == 10
        assert f.time_efficiency_percent(level=10) == 20

    def test_invalid_level_raises(self) -> None:
        """A level above 10 raises ValueError."""
        with pytest.raises(ValueError):
            f.time_efficiency_percent(level=11)


class TestEstimatedItemValue:
    def test_sums_quantity_times_adjusted_price(self) -> None:
        """EIV matches the Nano Pump material valuation."""
        materials = [
            f.MaterialValue(quantity=67, adjusted_price=1894.88),
            f.MaterialValue(quantity=100, adjusted_price=1794.01),
            f.MaterialValue(quantity=89, adjusted_price=28851.54),
        ]
        assert f.estimated_item_value(materials=materials) == pytest.approx(
            NANO_PUMP_EIV
        )

    def test_empty_is_zero(self) -> None:
        """No materials gives zero EIV."""
        assert f.estimated_item_value(materials=[]) == 0

    def test_negative_values_raise(self) -> None:
        """Negative quantities raise ValueError."""
        with pytest.raises(ValueError):
            f.estimated_item_value(
                materials=[f.MaterialValue(quantity=-1, adjusted_price=1)]
            )


class TestResearchProcessTimeValue:
    def test_in_game_nano_pump_zero_to_ten(self) -> None:
        """PTV matches the in-game 0 to 10 quote."""
        ptv = f.research_process_time_value(
            estimated_item_value=NANO_PUMP_EIV, start_level=0, target_level=10
        )
        assert round(ptv) == 140_148_786

    def test_in_game_nano_pump_zero_to_five(self) -> None:
        """PTV matches the in-game 0 to 5 quote."""
        ptv = f.research_process_time_value(
            estimated_item_value=NANO_PUMP_EIV, start_level=0, target_level=5
        )
        assert round(ptv) == 1_839_453

    def test_negative_eiv_raises(self) -> None:
        """Negative EIV raises ValueError."""
        with pytest.raises(ValueError):
            f.research_process_time_value(
                estimated_item_value=-1, start_level=0, target_level=1
            )


class TestSkillTimeFactor:
    def test_research_skills_compose_multiplicatively(self) -> None:
        """Level 5 skills give the in-game -36.25% factor."""
        factor = f.research_skill_time_factor(
            primary_skill_level=5, advanced_industry_level=5
        )
        assert factor == pytest.approx(0.6375)

    def test_untrained_is_one(self) -> None:
        """Untrained skills give no reduction."""
        assert (
            f.research_skill_time_factor(
                primary_skill_level=0, advanced_industry_level=0
            )
            == 1
        )

    @pytest.mark.parametrize(("primary", "advanced"), [(6, 0), (0, -1)])
    def test_invalid_skill_levels_raise(self, primary: int, advanced: int) -> None:
        """Skill levels outside 0 to 5 raise ValueError."""
        with pytest.raises(ValueError):
            f.research_skill_time_factor(
                primary_skill_level=primary, advanced_industry_level=advanced
            )


class TestResearchDuration:
    def test_in_game_unbonused_nano_pump(self) -> None:
        """Unbonused duration matches the in-game 44d 10h 40m."""
        seconds = f.research_duration_seconds(
            base_step_seconds=NANO_PUMP_BASE_STEP_SECONDS,
            start_level=0,
            target_level=10,
        )
        assert seconds == pytest.approx(44 * 86400 + 10 * 3600 + 40 * 60)

    def test_in_game_skilled_npc_station(self) -> None:
        """Skilled NPC-station duration matches the in-game 28d 8h."""
        seconds = f.research_duration_seconds(
            base_step_seconds=NANO_PUMP_BASE_STEP_SECONDS,
            start_level=0,
            target_level=10,
            time_factors=[0.6375],
        )
        assert seconds == pytest.approx(28 * 86400 + 8 * 3600)

    def test_in_game_skilled_structure_role_bonus(self) -> None:
        """Structure role bonus duration matches the in-game 22d 16h."""
        seconds = f.research_duration_seconds(
            base_step_seconds=NANO_PUMP_BASE_STEP_SECONDS,
            start_level=0,
            target_level=10,
            time_factors=[0.6375, f.bonus_to_factor(bonus=0.20)],
        )
        assert seconds == pytest.approx(22 * 86400 + 16 * 3600)

    def test_negative_factor_raises(self) -> None:
        """Negative time factors raise ValueError."""
        with pytest.raises(ValueError):
            f.research_duration_seconds(
                base_step_seconds=105,
                start_level=0,
                target_level=1,
                time_factors=[-0.1],
            )

    def test_non_positive_base_time_raises(self) -> None:
        """Non-positive base time raises ValueError."""
        with pytest.raises(ValueError):
            f.research_duration_seconds(
                base_step_seconds=0, start_level=0, target_level=1
            )


class TestBonusToFactor:
    def test_converts_reduction(self) -> None:
        """A 4% bonus becomes a 0.96 factor."""
        assert f.bonus_to_factor(bonus=0.04) == pytest.approx(0.96)

    @pytest.mark.parametrize("bonus", [-0.1, 1.1])
    def test_out_of_range_raises(self, bonus: float) -> None:
        """Bonuses outside 0 to 1 raise ValueError."""
        with pytest.raises(ValueError):
            f.bonus_to_factor(bonus=bonus)


class TestJobCost:
    def test_in_game_antimatter_npc_alpha(self) -> None:
        """Whole-ISK costs match the in-game Antimatter quote."""
        cost = f.job_cost(
            process_time_value=71_092.906666,
            system_cost_index=0.0525,
            facility_tax_rate=f.NPC_FACILITY_TAX_RATE,
            scc_rate=f.RESEARCH_SCC_RATE,
            alpha_tax_rate=f.ALPHA_CLONE_TAX_RATE,
        )
        whole = cost.to_whole_isk()
        assert whole.gross_job_cost == 3732
        assert whole.total_taxes == 1778
        assert whole.total_job_cost == 5510

    def test_in_game_structure_cost_bonus_omega(self) -> None:
        """Structure cost bonus matches the in-game Omega quote."""
        cost = f.job_cost(
            process_time_value=140_148_785.74,
            system_cost_index=0.0598,
            facility_tax_rate=0.0025,
            scc_rate=f.RESEARCH_SCC_RATE,
            cost_factors=[f.bonus_to_factor(bonus=0.04)],
        )
        assert cost.gross_job_cost == pytest.approx(8_044_842, rel=2e-4)
        assert cost.total_taxes == pytest.approx(3_153_347, abs=2)
        assert cost.alpha_tax == 0

    def test_components_sum(self) -> None:
        """Charges are computed from PTV and totals sum correctly."""
        cost = f.job_cost(
            process_time_value=1000,
            system_cost_index=0.1,
            facility_tax_rate=0.01,
            scc_rate=0.02,
            alpha_tax_rate=0.03,
            cost_factors=[0.5],
        )
        assert cost.gross_job_cost == pytest.approx(50)
        assert cost.facility_tax == pytest.approx(10)
        assert cost.scc_surcharge == pytest.approx(20)
        assert cost.alpha_tax == pytest.approx(30)
        assert cost.total_taxes == pytest.approx(60)
        assert cost.total_job_cost == pytest.approx(110)

    def test_cost_factors_do_not_discount_taxes(self) -> None:
        """Cost bonuses reduce only gross job cost."""
        base = f.job_cost(
            process_time_value=1000,
            system_cost_index=0.1,
            facility_tax_rate=0.01,
            scc_rate=0.02,
        )
        discounted = f.job_cost(
            process_time_value=1000,
            system_cost_index=0.1,
            facility_tax_rate=0.01,
            scc_rate=0.02,
            cost_factors=[0.96],
        )
        assert discounted.total_taxes == base.total_taxes

    def test_negative_rate_raises(self) -> None:
        """Negative rates raise ValueError."""
        with pytest.raises(ValueError):
            f.job_cost(
                process_time_value=1000,
                system_cost_index=-0.1,
                facility_tax_rate=0.01,
                scc_rate=0.02,
            )


class TestRoundIskHalfUp:
    @pytest.mark.parametrize(
        ("value", "expected"), [(0.5, 1), (1.5, 2), (2.5, 3), (2.49, 2), (0, 0)]
    )
    def test_rounds_half_up(self, value: float, expected: int) -> None:
        """Halves round up rather than to even."""
        assert f.round_isk_half_up(value) == expected


HOBGOBLIN_II_EIV = 101_786.09


class TestInventionSuccessChance:
    def test_in_game_hobgoblin_all_fives(self) -> None:
        """All-five skills give the in-game 49.6% chance."""
        chance = f.invention_success_chance(
            base_chance=0.34,
            science_skill_levels=(5, 5),
            encryption_skill_level=5,
        )
        assert chance == pytest.approx(0.495833, abs=1e-6)
        assert round(chance * 100, 1) == 49.6

    def test_decryptor_modifier_multiplies(self) -> None:
        """A decryptor probability modifier multiplies the skilled chance."""
        chance = f.invention_success_chance(
            base_chance=0.34,
            science_skill_levels=(0, 0),
            encryption_skill_level=0,
            decryptor=f.DECRYPTORS["Attainment"],
        )
        assert chance == pytest.approx(0.34 * 1.8)

    def test_chance_is_capped_at_one(self) -> None:
        """Chance never exceeds certainty (hypothetical base chance)."""
        chance = f.invention_success_chance(
            base_chance=0.6,
            science_skill_levels=(5, 5),
            encryption_skill_level=5,
            decryptor=f.DECRYPTORS["Optimized Attainment"],
        )
        assert chance == 1

    @pytest.mark.parametrize(
        ("base", "science", "encryption"),
        [(-0.1, (5, 5), 5), (1.1, (5, 5), 5), (0.3, (6, 5), 5), (0.3, (5,), 5)],
    )
    def test_invalid_inputs_raise(
        self, base: float, science: tuple[int, ...], encryption: int
    ) -> None:
        """Invalid chance, skill level, or skill count raises ValueError."""
        with pytest.raises(ValueError):
            f.invention_success_chance(
                base_chance=base,
                science_skill_levels=science,
                encryption_skill_level=encryption,
            )


class TestDecryptors:
    def test_table_has_eight_decryptors(self) -> None:
        """All eight standard decryptors are defined."""
        assert len(f.DECRYPTORS) == 8

    def test_augmentation_values(self) -> None:
        """Augmentation matches the EVE University table."""
        d = f.DECRYPTORS["Augmentation"]
        assert (d.type_id, d.probability_modifier, d.runs, d.me, d.te) == (
            34203,
            -0.40,
            9,
            -2,
            2,
        )


class TestInventedBlueprint:
    def test_without_decryptor(self) -> None:
        """Without a decryptor the output has base runs, ME 2, and TE 4."""
        bp = f.invented_blueprint(base_runs=10)
        assert (bp.runs, bp.me, bp.te) == (10, 2, 4)

    def test_with_decryptor(self) -> None:
        """Decryptor modifiers add to the base output attributes."""
        bp = f.invented_blueprint(base_runs=1, decryptor=f.DECRYPTORS["Augmentation"])
        assert (bp.runs, bp.me, bp.te) == (10, 0, 6)

    def test_non_positive_runs_raise(self) -> None:
        """Base runs must be positive."""
        with pytest.raises(ValueError):
            f.invented_blueprint(base_runs=0)


class TestInventionProcessTimeValue:
    def test_in_game_hobgoblin(self) -> None:
        """PTV is 2% of the T2 blueprint's EIV."""
        assert f.invention_process_time_value(
            estimated_item_value=HOBGOBLIN_II_EIV
        ) == pytest.approx(2035.7218)

    def test_attempts_multiply(self) -> None:
        """PTV scales with the number of attempts (assumed)."""
        assert f.invention_process_time_value(
            estimated_item_value=1000, attempts=3
        ) == pytest.approx(60)

    @pytest.mark.parametrize(("eiv", "attempts"), [(-1, 1), (1, 0)])
    def test_invalid_inputs_raise(self, eiv: float, attempts: int) -> None:
        """Negative EIV or non-positive attempts raise ValueError."""
        with pytest.raises(ValueError):
            f.invention_process_time_value(estimated_item_value=eiv, attempts=attempts)

    def test_in_game_hobgoblin_job_cost(self) -> None:
        """Whole-ISK job cost matches the in-game Osmeden quote."""
        ptv = f.invention_process_time_value(estimated_item_value=HOBGOBLIN_II_EIV)
        whole = f.job_cost(
            process_time_value=ptv,
            system_cost_index=0.0488,
            facility_tax_rate=f.NPC_FACILITY_TAX_RATE,
            scc_rate=f.INVENTION_SCC_RATE,
        ).to_whole_isk()
        assert (whole.gross_job_cost, whole.total_taxes, whole.total_job_cost) == (
            99,
            86,
            185,
        )


class TestInventionDuration:
    def test_in_game_hobgoblin_advanced_industry_five(self) -> None:
        """Advanced Industry 5 gives the in-game 01:50:30."""
        seconds = f.invention_duration_seconds(
            base_seconds=7800,
            time_factors=[f.advanced_industry_time_factor(level=5)],
        )
        assert seconds == pytest.approx(1 * 3600 + 50 * 60 + 30)

    def test_attempts_multiply(self) -> None:
        """Duration scales with attempts (assumed)."""
        assert f.invention_duration_seconds(base_seconds=100, attempts=2) == 200

    def test_non_positive_base_time_raises(self) -> None:
        """Base time must be positive."""
        with pytest.raises(ValueError):
            f.invention_duration_seconds(base_seconds=0)


class TestAdvancedIndustryTimeFactor:
    def test_levels(self) -> None:
        """Each level reduces time by 3%."""
        assert f.advanced_industry_time_factor(level=0) == 1
        assert f.advanced_industry_time_factor(level=5) == pytest.approx(0.85)

    def test_invalid_level_raises(self) -> None:
        """Levels outside 0 to 5 raise ValueError."""
        with pytest.raises(ValueError):
            f.advanced_industry_time_factor(level=6)


class TestInventionProbabilityHelpers:
    def test_expected_attempts_per_success(self) -> None:
        """Expected attempts is the reciprocal of the chance."""
        assert f.expected_attempts_per_success(success_chance=0.25) == 4

    def test_probability_of_at_least_one_success(self) -> None:
        """At least one success is the complement of all failures."""
        assert f.probability_of_at_least_one_success(
            success_chance=0.5, attempts=3
        ) == pytest.approx(0.875)

    def test_attempts_for_confidence(self) -> None:
        """Minimum attempts reaching the confidence target."""
        assert f.attempts_for_confidence(success_chance=0.5, confidence=0.875) == 3
        assert f.attempts_for_confidence(success_chance=0.5, confidence=0.9) == 4
        assert f.attempts_for_confidence(success_chance=1, confidence=0.99) == 1

    def test_expected_cost_per_success(self) -> None:
        """Per-attempt cost divided by the chance."""
        assert f.expected_cost_per_success(
            cost_per_attempt=100, success_chance=0.25
        ) == pytest.approx(400)

    @pytest.mark.parametrize("chance", [0, -0.1, 1.1])
    def test_invalid_chance_raises(self, chance: float) -> None:
        """Chance must be in (0, 1]."""
        with pytest.raises(ValueError):
            f.expected_attempts_per_success(success_chance=chance)

    @pytest.mark.parametrize("confidence", [0, 1, 1.5])
    def test_invalid_confidence_raises(self, confidence: float) -> None:
        """Confidence must be in (0, 1)."""
        with pytest.raises(ValueError):
            f.attempts_for_confidence(success_chance=0.5, confidence=confidence)


class TestInventionInputs:
    def test_in_game_two_runs_with_decryptor(self) -> None:
        """Datacores and decryptors are consumed per attempt (in-game)."""
        inputs = f.invention_inputs(
            materials_per_attempt={20420: 1, 20419: 1},
            attempts=2,
            decryptor=f.DECRYPTORS["Attainment"],
        )
        assert inputs == {20420: 2, 20419: 2, 34202: 2}

    def test_without_decryptor(self) -> None:
        """Only datacores are consumed without a decryptor."""
        assert f.invention_inputs(materials_per_attempt={1: 3}, attempts=1) == {1: 3}

    def test_decryptor_type_also_listed_as_material_is_summed(self) -> None:
        """Duplicate type IDs are summed rather than overwritten."""
        inputs = f.invention_inputs(
            materials_per_attempt={34202: 1},
            attempts=1,
            decryptor=f.DECRYPTORS["Attainment"],
        )
        assert inputs == {34202: 2}

    @pytest.mark.parametrize(("materials", "attempts"), [({1: -1}, 1), ({1: 1}, 0)])
    def test_invalid_inputs_raise(
        self, materials: dict[int, int], attempts: int
    ) -> None:
        """Negative quantities or non-positive attempts raise ValueError."""
        with pytest.raises(ValueError):
            f.invention_inputs(materials_per_attempt=materials, attempts=attempts)


class TestInGameDecryptorTwoRuns:
    def test_hobgoblin_attainment_two_runs(self) -> None:
        """Two runs with Attainment match the in-game quote."""
        chance = f.invention_success_chance(
            base_chance=0.34,
            science_skill_levels=(5, 5),
            encryption_skill_level=5,
            decryptor=f.DECRYPTORS["Attainment"],
        )
        assert chance == pytest.approx(0.8925)
        bp = f.invented_blueprint(base_runs=10, decryptor=f.DECRYPTORS["Attainment"])
        assert (bp.runs, bp.me, bp.te) == (14, 1, 8)
        ptv = f.invention_process_time_value(
            estimated_item_value=HOBGOBLIN_II_EIV, attempts=2
        )
        whole = f.job_cost(
            process_time_value=ptv,
            system_cost_index=0.0488,
            facility_tax_rate=f.NPC_FACILITY_TAX_RATE,
            scc_rate=f.INVENTION_SCC_RATE,
        ).to_whole_isk()
        assert (whole.gross_job_cost, whole.total_taxes, whole.total_job_cost) == (
            199,
            173,
            372,
        )
        seconds = f.invention_duration_seconds(
            base_seconds=7800,
            attempts=2,
            time_factors=[f.advanced_industry_time_factor(level=5)],
        )
        assert seconds == pytest.approx(3 * 3600 + 41 * 60)


class TestManufacturingMaterialQuantity:
    @pytest.mark.parametrize(
        ("base", "runs", "expected"),
        [(509, 10, 4581), (7, 10, 63), (4, 10, 36), (2, 10, 18), (509, 1, 459)],
    )
    def test_in_game_hobgoblin_i_me10(
        self, base: int, runs: int, expected: int
    ) -> None:
        """ME10 quantities match the in-game Hobgoblin I quote."""
        assert (
            f.manufacturing_material_quantity(
                base_quantity=base, runs=runs, material_efficiency=10
            )
            == expected
        )

    def test_minimum_one_per_run(self) -> None:
        """At least one unit per run is required (in-game ME1 Hobgoblin II)."""
        assert (
            f.manufacturing_material_quantity(
                base_quantity=1, runs=10, material_efficiency=1
            )
            == 10
        )

    def test_in_game_cap_booster_raitaru_with_rig(self) -> None:
        """ME10 with Raitaru 1% and a 2% rig matches the in-game quote."""
        assert f.manufacturing_materials(
            base_materials={34: 1951, 35: 398, 36: 167, 37: 13, 39: 4, 40: 2},
            runs=10,
            material_efficiency=10,
            material_factors=[
                f.bonus_to_factor(bonus=0.01),
                f.bonus_to_factor(bonus=0.02),
            ],
        ) == {34: 17036, 35: 3476, 36: 1459, 37: 114, 39: 35, 40: 18}

    def test_rounds_to_two_decimals_before_ceil(self) -> None:
        """58.0041 rounds to 58.00 before ceil (community-reported rule)."""
        assert (
            f.manufacturing_material_quantity(
                base_quantity=21,
                runs=3,
                material_efficiency=7,
                material_factors=[0.99],
            )
            == 58
        )

    def test_per_job_rounding_beats_per_run(self) -> None:
        """One 3-run job uses less than three 1-run jobs."""
        one_job = f.manufacturing_material_quantity(
            base_quantity=509, runs=3, material_efficiency=10
        )
        single = f.manufacturing_material_quantity(
            base_quantity=509, runs=1, material_efficiency=10
        )
        assert one_job == 1375
        assert 3 * single == 1377

    def test_zero_base_quantity_is_zero(self) -> None:
        """A zero base quantity needs nothing."""
        assert (
            f.manufacturing_material_quantity(
                base_quantity=0, runs=5, material_efficiency=0
            )
            == 0
        )

    @pytest.mark.parametrize(
        ("base", "runs", "me", "factors"),
        [(-1, 1, 0, ()), (1, 0, 0, ()), (1, 1, 11, ()), (1, 1, 0, (-0.1,))],
    )
    def test_invalid_inputs_raise(
        self, base: int, runs: int, me: int, factors: tuple[float, ...]
    ) -> None:
        """Invalid quantities, runs, ME, or factors raise ValueError."""
        with pytest.raises(ValueError):
            f.manufacturing_material_quantity(
                base_quantity=base,
                runs=runs,
                material_efficiency=me,
                material_factors=factors,
            )


class TestManufacturingMaterials:
    def test_maps_each_material(self) -> None:
        """Each material is calculated independently by type ID."""
        assert f.manufacturing_materials(
            base_materials={34: 509, 35: 7, 37: 4, 38: 2},
            runs=10,
            material_efficiency=10,
        ) == {34: 4581, 35: 63, 37: 36, 38: 18}


class TestManufacturingProcessTimeValue:
    def test_eiv_times_runs(self) -> None:
        """PTV is EIV times runs."""
        assert f.manufacturing_process_time_value(
            estimated_item_value=3491.31, runs=10
        ) == pytest.approx(34913.1)

    @pytest.mark.parametrize(("eiv", "runs"), [(-1, 1), (1, 0)])
    def test_invalid_inputs_raise(self, eiv: float, runs: int) -> None:
        """Negative EIV or non-positive runs raise ValueError."""
        with pytest.raises(ValueError):
            f.manufacturing_process_time_value(estimated_item_value=eiv, runs=runs)

    def test_in_game_hobgoblin_i_cost_is_close(self) -> None:
        """Job cost is within a few ISK of the in-game 2,741."""
        ptv = f.manufacturing_process_time_value(estimated_item_value=3491.31, runs=10)
        whole = f.job_cost(
            process_time_value=ptv,
            system_cost_index=0.0361,
            facility_tax_rate=f.NPC_FACILITY_TAX_RATE,
            scc_rate=f.MANUFACTURING_SCC_RATE,
        ).to_whole_isk()
        assert whole.total_job_cost == pytest.approx(2741, abs=5)


class TestManufacturingSkillTimeFactors:
    def test_industry_factor(self) -> None:
        """Industry reduces time 4% per level."""
        assert f.industry_time_factor(level=5) == pytest.approx(0.8)

    def test_science_skill_factor(self) -> None:
        """Each T2 science skill reduces time 1% per level."""
        assert f.science_skill_manufacturing_time_factor(level=5) == pytest.approx(0.95)

    def test_in_game_t2_skill_total(self) -> None:
        """Four skills at 5 give the in-game -38.6% skill bonus."""
        factor = (
            f.industry_time_factor(level=5)
            * f.advanced_industry_time_factor(level=5)
            * f.science_skill_manufacturing_time_factor(level=5) ** 2
        )
        assert factor == pytest.approx(0.6137)

    @pytest.mark.parametrize("level", [-1, 6])
    def test_invalid_levels_raise(self, level: int) -> None:
        """Levels outside 0 to 5 raise ValueError."""
        with pytest.raises(ValueError):
            f.industry_time_factor(level=level)
        with pytest.raises(ValueError):
            f.science_skill_manufacturing_time_factor(level=level)


class TestManufacturingDuration:
    def test_in_game_hobgoblin_i_te20(self) -> None:
        """TE20, Industry 5, Advanced Industry 5 gives the in-game 0:27:12."""
        seconds = f.manufacturing_duration_seconds(
            base_seconds=300,
            runs=10,
            time_efficiency=20,
            time_factors=[
                f.industry_time_factor(level=5),
                f.advanced_industry_time_factor(level=5),
            ],
        )
        assert seconds == pytest.approx(27 * 60 + 12)

    def test_in_game_hobgoblin_ii_te8_t2_skills(self) -> None:
        """TE8 with four skills at 5 gives the in-game 2:21:09."""
        seconds = f.manufacturing_duration_seconds(
            base_seconds=1500,
            runs=10,
            time_efficiency=8,
            time_factors=[
                f.industry_time_factor(level=5),
                f.advanced_industry_time_factor(level=5),
                f.science_skill_manufacturing_time_factor(level=5),
                f.science_skill_manufacturing_time_factor(level=5),
            ],
        )
        assert round(seconds) == 2 * 3600 + 21 * 60 + 9

    @pytest.mark.parametrize(("base", "runs", "te"), [(0, 1, 0), (1, 0, 0), (1, 1, 21)])
    def test_invalid_inputs_raise(self, base: float, runs: int, te: int) -> None:
        """Invalid base time, runs, or TE raise ValueError."""
        with pytest.raises(ValueError):
            f.manufacturing_duration_seconds(
                base_seconds=base, runs=runs, time_efficiency=te
            )

    def test_in_game_cap_booster_raitaru_time(self) -> None:
        """Raitaru 15% time bonus gives the in-game 0:46:14."""
        seconds = f.manufacturing_duration_seconds(
            base_seconds=600,
            runs=10,
            time_efficiency=20,
            time_factors=[
                f.industry_time_factor(level=5),
                f.advanced_industry_time_factor(level=5),
                f.bonus_to_factor(bonus=0.15),
            ],
        )
        assert round(seconds) == 46 * 60 + 14


class TestCopyingProcessTimeValue:
    def test_scales_with_runs_and_copies(self) -> None:
        """PTV is 2% of EIV per licensed run, across all copies."""
        assert f.copying_process_time_value(
            estimated_item_value=1000, runs_per_copy=10, copies=2
        ) == pytest.approx(400)

    def test_in_game_nano_pump_osmeden_fees(self) -> None:
        """Nano Pump 1x10 copy in Osmeden (SCI 4.09%) matches in-game fees."""
        ptv = f.copying_process_time_value(
            estimated_item_value=NANO_PUMP_EIV, runs_per_copy=10, copies=1
        )
        cost = f.job_cost(
            process_time_value=ptv,
            system_cost_index=0.0409,
            facility_tax_rate=f.NPC_FACILITY_TAX_RATE,
            scc_rate=f.COPYING_SCC_RATE,
        ).to_whole_isk()
        assert (cost.gross_job_cost, cost.facility_tax, cost.scc_surcharge) == (
            23_511,
            1_437,
            22_993,
        )

    @pytest.mark.parametrize(
        ("eiv", "runs", "copies", "limit"),
        [(-1, 1, 1, None), (1, 0, 1, None), (1, 1, 0, None), (1, 41, 1, 40)],
    )
    def test_invalid_inputs_raise(
        self, eiv: float, runs: int, copies: int, limit: int | None
    ) -> None:
        """Negative EIV, non-positive counts, or runs over the limit raise."""
        with pytest.raises(ValueError):
            f.copying_process_time_value(
                estimated_item_value=eiv,
                runs_per_copy=runs,
                copies=copies,
                max_runs_per_copy=limit,
            )

    def test_runs_at_limit_allowed(self) -> None:
        """Runs equal to the blueprint's limit are allowed."""
        assert f.copying_process_time_value(
            estimated_item_value=1, runs_per_copy=40, copies=1, max_runs_per_copy=40
        ) == pytest.approx(0.8)


class TestScienceCopyTimeFactor:
    @pytest.mark.parametrize(("level", "factor"), [(0, 1.0), (3, 0.85), (5, 0.75)])
    def test_five_percent_per_level(self, level: int, factor: float) -> None:
        """Science reduces copy time by 5% per level."""
        assert f.science_copy_time_factor(level=level) == pytest.approx(factor)

    def test_invalid_level_raises(self) -> None:
        """Levels outside 0 to 5 raise ValueError."""
        with pytest.raises(ValueError):
            f.science_copy_time_factor(level=6)


class TestCopyingDuration:
    def test_unbonused(self) -> None:
        """Duration is base time per run times runs times copies."""
        assert f.copying_duration_seconds(
            base_seconds=3600, runs_per_copy=10, copies=2
        ) == pytest.approx(72_000)

    def test_in_game_nano_pump_npc_skills(self) -> None:
        """Science 5 and Advanced Industry 5 give the in-game 6:22:30."""
        seconds = f.copying_duration_seconds(
            base_seconds=3600,
            runs_per_copy=10,
            copies=1,
            time_factors=[
                f.science_copy_time_factor(level=5),
                f.advanced_industry_time_factor(level=5),
            ],
        )
        assert round(seconds) == 6 * 3600 + 22 * 60 + 30

    @pytest.mark.parametrize(
        ("base", "runs", "copies"), [(0, 1, 1), (1, 0, 1), (1, 1, 0)]
    )
    def test_invalid_inputs_raise(self, base: float, runs: int, copies: int) -> None:
        """Non-positive base time, runs, or copies raise ValueError."""
        with pytest.raises(ValueError):
            f.copying_duration_seconds(
                base_seconds=base, runs_per_copy=runs, copies=copies
            )
