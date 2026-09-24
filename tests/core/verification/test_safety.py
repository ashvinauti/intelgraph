from intelgraph.core.verification.safety import SafetyChecker, SafetyReport


def test_safety_report_defaults():
    r = SafetyReport()
    assert r.is_safe
    assert r.severity == "NONE"


def test_safety_report_severity_high():
    r = SafetyReport(flags=["source dominance: ..."])
    assert not r.is_safe
    assert r.severity == "HIGH"


def test_safety_report_severity_medium():
    r = SafetyReport(flags=["domain bias: ..."])
    assert r.severity == "MEDIUM"


def test_safety_report_severity_low():
    r = SafetyReport(flags=["minor flag"])
    assert r.severity == "LOW"


def test_check_source_dominance_high():
    flags = SafetyChecker.check_source_dominance([80, 10, 10])
    assert len(flags) == 1
    assert "dominance" in flags[0]


def test_check_source_dominance_ok():
    flags = SafetyChecker.check_source_dominance([40, 30, 30])
    assert len(flags) == 0


def test_check_source_dominance_empty():
    flags = SafetyChecker.check_source_dominance([])
    assert len(flags) == 0


def test_check_domain_bias():
    domains = [
        "https://source1.com/page1",
        "https://source1.com/page2",
        "https://source2.com/page1",
    ]
    flags = SafetyChecker.check_domain_bias(domains)
    assert len(flags) == 1
    assert "domain bias" in flags[0]
    assert "source1.com" in flags[0]


def test_check_domain_bias_no_bias():
    domains = [
        "https://source1.com/page1",
        "https://source2.com/page1",
        "https://source3.com/page1",
    ]
    flags = SafetyChecker.check_domain_bias(domains)
    assert len(flags) == 0


def test_check_domain_bias_too_few():
    flags = SafetyChecker.check_domain_bias(["https://example.com/page1"])
    assert len(flags) == 0


def test_check_rapid_change():
    flags = SafetyChecker.check_rapid_change(50.0, 90.0)
    assert len(flags) == 1
    assert "rapid change" in flags[0]


def test_check_rapid_change_within_threshold():
    flags = SafetyChecker.check_rapid_change(50.0, 65.0)
    assert len(flags) == 0


def test_check_rapid_change_zero_previous():
    flags = SafetyChecker.check_rapid_change(0.0, 50.0)
    assert len(flags) == 0


def test_check_contradiction_for_confirmed():
    flags = SafetyChecker.check_contradiction_for_confirmed(30.0, "confirmed")
    assert len(flags) == 1
    assert "contradiction" in flags[0]


def test_check_contradiction_for_confirmed_ok():
    flags = SafetyChecker.check_contradiction_for_confirmed(10.0, "confirmed")
    assert len(flags) == 0


def test_full_check_all_clear():
    report = SafetyChecker.full_check(
        source_trust_scores=[30, 35, 35],
        source_domains=[
            "https://a.com/p1",
            "https://b.com/p1",
            "https://c.com/p1",
        ],
        contradiction=10.0,
        verification_state="confirmed",
    )
    assert report.is_safe
    assert len(report.flags) == 0


def test_full_check_with_flags():
    report = SafetyChecker.full_check(
        source_trust_scores=[80, 10, 10],
        source_domains=[
            "https://biased.com/p1",
            "https://biased.com/p2",
            "https://other.com/p1",
        ],
        contradiction=30.0,
        verification_state="confirmed",
    )
    assert not report.is_safe
    assert len(report.flags) >= 2
