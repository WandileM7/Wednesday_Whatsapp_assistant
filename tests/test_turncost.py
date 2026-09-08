"""The backend router: measured rates, the turn estimate, and the hysteresis."""
import pytest

from backend import turncost
from backend.config import settings


@pytest.fixture(autouse=True)
def _clean():
    """Each test starts on the seeds with no sticky channels."""
    turncost._PREFILL.clear(); turncost._DECODE.clear(); turncost._MISS.clear()
    turncost._ON_HOSTED.clear()
    yield
    turncost._PREFILL.clear(); turncost._DECODE.clear(); turncost._MISS.clear()
    turncost._ON_HOSTED.clear()


def _prompt(tokens: int) -> list[dict]:
    """A context of roughly `tokens` tokens (4 chars each, 8 per message)."""
    return [{"role": "system", "content": "x" * ((tokens - 8) * 4)}]


def _final(evaluated, prefill_s, decoded, decode_s):
    """An Ollama done-chunk. Durations are nanoseconds on the wire."""
    return {"done": True,
            "prompt_eval_count": evaluated, "prompt_eval_duration": int(prefill_s * 1e9),
            "eval_count": decoded, "eval_duration": int(decode_s * 1e9)}


# --- observation ----------------------------------------------------------

def test_rates_start_on_the_seed_and_say_so():
    assert turncost.rates() == (turncost._SEED_PREFILL, turncost._SEED_DECODE,
                                turncost._SEED_MISS)
    assert not turncost.measured()


def test_observe_learns_the_real_rate_off_ollamas_counters():
    turncost.observe(1000, _final(evaluated=600, prefill_s=100.0,
                                  decoded=50, decode_s=25.0))
    prefill, decode, miss = turncost.rates()
    assert prefill == pytest.approx(6.0)      # the CPU fallback, unmistakably
    assert decode == pytest.approx(2.0)
    assert miss == pytest.approx(0.6)
    assert turncost.measured()


def test_a_fully_cached_prompt_is_a_miss_sample_not_a_rate_sample():
    """The warm case reports nothing to evaluate. That is real information about
    the cache and no information about throughput — recording it as a zero rate
    would drag the median to the floor and route everything hosted."""
    turncost.observe(2800, _final(evaluated=0, prefill_s=0, decoded=40, decode_s=2.0))
    prefill, _, miss = turncost.rates()
    assert miss == 0.0
    assert prefill == turncost._SEED_PREFILL, "no prefill work means no prefill sample"


def test_rates_use_the_median_so_one_cold_load_does_not_stick():
    for _ in range(5):
        turncost.observe(1000, _final(600, 8.0, 50, 2.5))     # ~75 tok/s
    turncost.observe(1000, _final(600, 600.0, 50, 2.5))       # one cold outlier
    prefill, _, _ = turncost.rates()
    assert prefill == pytest.approx(75.0), "a mean would still be carrying the outlier"


def test_observe_survives_a_chunk_with_no_counters():
    turncost.observe(1000, {"done": True})
    assert not turncost.measured()


# --- the estimate ---------------------------------------------------------

def test_a_tool_turn_costs_more_than_a_bare_one():
    """A matched intent group means a second round carrying the tool result,
    which is the single biggest term in the estimate."""
    bare = turncost.estimate(_prompt(2000), [], "thanks")
    tooled = turncost.estimate(_prompt(2000), [], "play something moody")
    assert bare.hops == 1 and tooled.hops == 2
    assert tooled.seconds > bare.seconds


def test_an_ask_for_long_form_costs_more_to_decode():
    short = turncost.estimate(_prompt(2000), [], "what time is it")
    long = turncost.estimate(_prompt(2000), [], "explain how load shedding stages work")
    assert long.decode_tokens > short.decode_tokens
    assert long.seconds > short.seconds


def test_tool_schemas_count_towards_the_prompt():
    """They are thousands of tokens and they are sent every turn; leaving them
    out would understate every turn that carries them."""
    schemas = [{"type": "function", "function": {"name": "x" * 400}}]
    without = turncost.estimate(_prompt(1000), [], "hi")
    with_ = turncost.estimate(_prompt(1000), schemas, "hi")
    assert with_.prompt_tokens > without.prompt_tokens


def test_a_slow_box_is_reflected_in_the_estimate():
    fast = turncost.estimate(_prompt(3000), [], "hi").seconds
    turncost.observe(1000, _final(evaluated=600, prefill_s=100.0,   # 6 tok/s
                                  decoded=50, decode_s=25.0))       # 2 tok/s
    slow = turncost.estimate(_prompt(3000), [], "hi").seconds
    assert slow > fast * 5, "the CPU fallback has to show up as an order of magnitude"


# --- the decision ---------------------------------------------------------

def _est(seconds):
    return turncost.Estimate(prompt_tokens=0, prefill_tokens=0, decode_tokens=0,
                             hops=1, seconds=seconds)


def test_a_cheap_turn_stays_local_and_an_expensive_one_does_not():
    budget = settings.route_latency_budget
    assert not turncost.prefer_hosted("wandile", _est(budget - 1))
    assert turncost.prefer_hosted("wandile", _est(budget * 4))


def test_she_does_not_flip_backend_around_the_boundary():
    """Hosted and local do not sound the same — hosted has no min_p, so it runs
    nearer the middle. A turn sitting on the threshold must not switch her voice
    every other message, so coming back needs to be clearly cheap."""
    budget = settings.route_latency_budget
    turncost.prefer_hosted("wandile", _est(budget * 4))          # over: go hosted
    assert turncost.prefer_hosted("wandile", _est(budget * 0.9)), \
        "just under budget is not clearly under it — stay put"
    assert not turncost.prefer_hosted("wandile", _est(budget * 0.2)), \
        "clearly cheap brings her home"


def test_stickiness_is_per_channel():
    budget = settings.route_latency_budget
    turncost.prefer_hosted("whatsapp:271", _est(budget * 4))
    assert not turncost.prefer_hosted("wandile", _est(budget * 0.9)), \
        "one conversation going hosted must not drag another with it"


def test_forget_drops_the_sticky_backend():
    turncost.prefer_hosted("wandile", _est(settings.route_latency_budget * 4))
    turncost.forget("wandile")
    assert not turncost.prefer_hosted("wandile", _est(settings.route_latency_budget * 0.9))
