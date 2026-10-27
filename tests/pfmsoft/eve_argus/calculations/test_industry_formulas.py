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
