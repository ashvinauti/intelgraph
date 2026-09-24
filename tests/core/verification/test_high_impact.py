from intelgraph.core.verification.base import VerificationState
from intelgraph.core.verification.high_impact import HighImpactHandler


def test_person_with_title_ceo():
    assert HighImpactHandler.is_high_impact("person", title="CEO of Acme Corp")


def test_person_with_keyword_in_name():
    assert HighImpactHandler.is_high_impact("person", name="President Biden")


def test_person_no_high_impact():
    assert not HighImpactHandler.is_high_impact("person", name="John Doe", title="Engineer")


def test_company_finance():
    assert HighImpactHandler.is_high_impact("company", name="Goldman Sachs", industry="finance")


def test_company_healthcare():
    assert HighImpactHandler.is_high_impact("company", name="Pfizer", industry="healthcare")


def test_company_gov_domain():
    assert HighImpactHandler.is_high_impact(
        "company", name="GovWorks", industry="technology", domain="gov"
    )


def test_company_no_high_impact():
    assert not HighImpactHandler.is_high_impact("company", name="MomAndPop Shop", industry="retail")


def test_domain_never_high_impact():
    assert not HighImpactHandler.is_high_impact("domain", name="example.com")


def test_certificate_never_high_impact():
    assert not HighImpactHandler.is_high_impact("certificate", name="SHA256-...")


def test_requires_confirmed():
    assert HighImpactHandler.requires_confirmed("person", title="CEO")
    assert not HighImpactHandler.requires_confirmed("person", name="John", title="Intern")


def test_verification_requirement_standard():
    req = HighImpactHandler.verification_requirement(
        VerificationState.CONFIRMED, is_high_impact=False
    )
    assert req == "standard"


def test_verification_requirement_verified():
    req = HighImpactHandler.verification_requirement(
        VerificationState.CONFIRMED, is_high_impact=True
    )
    assert req == "verified"


def test_verification_requirement_requires_confirmed():
    req = HighImpactHandler.verification_requirement(
        VerificationState.PROBABLE, is_high_impact=True
    )
    assert req == "requires_confirmed"


def test_known_names():
    handler = HighImpactHandler()
    assert not handler.is_high_impact("person", name="Unknown Person", title="Janitor")
