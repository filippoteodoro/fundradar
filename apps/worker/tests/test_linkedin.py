"""
Tests for LinkedIn scraping module.

Tests the post classifier, profile classifier, and data normalization
without making actual API calls.
"""

import pytest
from datetime import datetime

from fundradar_worker.linkedin.posts_scraper import LinkedInPost, normalize_post
from fundradar_worker.linkedin.people_scraper import (
    LinkedInProfile,
    LinkedInEmployee,
    Experience,
    Education,
    normalize_profile,
    normalize_employee,
)
from fundradar_worker.linkedin.post_classifier import (
    PostClassifier,
    SignalType,
    ClassifiedPost,
)
from fundradar_worker.linkedin.profile_classifier import (
    ProfileClassifier,
    ClassifiedProfile,
    BackgroundType,
    SeniorityLevel,
)
from fundradar_worker.linkedin.people_stats import (
    FundPeopleStats,
    PeopleStatsCalculator,
)


# Test data fixtures
@pytest.fixture
def deal_post():
    """A post announcing a new investment."""
    return LinkedInPost(
        post_id="test-001",
        company_slug="test-fund",
        company_name="Test Fund",
        text="We're pleased to announce our investment in TechCorp, a leading SaaS company. "
             "This investment of €50 million will support their European expansion.",
        post_type="update",
        published_at="2026-01-20T10:00:00Z",
        engagement={"likes": 500, "comments": 50},
        source_url="https://linkedin.com/posts/test",
    )


@pytest.fixture
def exit_post():
    """A post announcing an exit."""
    return LinkedInPost(
        post_id="test-002",
        company_slug="test-fund",
        company_name="Test Fund",
        text="Congratulations to HealthCo on their acquisition by BigPharma! "
             "We've successfully exited our investment after 5 years of growth.",
        post_type="update",
        published_at="2026-01-15T10:00:00Z",
        engagement={"likes": 800, "comments": 100},
        source_url="https://linkedin.com/posts/test2",
    )


@pytest.fixture
def fundraise_post():
    """A post announcing a new fund."""
    return LinkedInPost(
        post_id="test-003",
        company_slug="test-fund",
        company_name="Test Fund",
        text="We're excited to announce the final close of Fund IV at €500 million. "
             "Thank you to all our LPs for their continued support.",
        post_type="update",
        published_at="2026-01-10T10:00:00Z",
        engagement={"likes": 1200, "comments": 150},
        source_url="https://linkedin.com/posts/test3",
    )


@pytest.fixture
def hire_post():
    """A post announcing a new hire."""
    return LinkedInPost(
        post_id="test-004",
        company_slug="test-fund",
        company_name="Test Fund",
        text="We're pleased to welcome Marco Rossi to our team as Partner. "
             "Marco joins us from Goldman Sachs where he led the Italian M&A practice.",
        post_type="update",
        published_at="2026-01-05T10:00:00Z",
        engagement={"likes": 300, "comments": 40},
        source_url="https://linkedin.com/posts/test4",
    )


@pytest.fixture
def generic_post():
    """A generic post without signals."""
    return LinkedInPost(
        post_id="test-005",
        company_slug="test-fund",
        company_name="Test Fund",
        text="Great weather today at our Milan office!",
        post_type="update",
        published_at="2026-01-01T10:00:00Z",
        engagement={"likes": 10, "comments": 2},
        source_url="https://linkedin.com/posts/test5",
    )


@pytest.fixture
def ib_profile():
    """A profile with investment banking background."""
    return LinkedInProfile(
        profile_id="ib-person",
        profile_url="https://linkedin.com/in/ib-person",
        name="Francesco Bianchi",
        headline="Partner at Test Fund",
        location="Milan, Italy",
        connections=500,
        about="Private equity investor with IB background",
        education=[
            Education(
                school="SDA Bocconi",
                degree="MBA",
                field_of_study="Finance",
                start_year=2010,
                end_year=2012,
            ),
            Education(
                school="Politecnico di Milano",
                degree="BSc",
                field_of_study="Engineering",
                start_year=2005,
                end_year=2009,
            ),
        ],
        experience=[
            Experience(
                company="Test Fund",
                title="Partner",
                location="Milan",
                start_date="2020-01",
                end_date=None,
                is_current=True,
                description="Leading investments in TMT sector",
            ),
            Experience(
                company="Goldman Sachs",
                title="Vice President",
                location="London",
                start_date="2015-01",
                end_date="2019-12",
                is_current=False,
                description="M&A advisory",
            ),
            Experience(
                company="Morgan Stanley",
                title="Analyst",
                location="London",
                start_date="2012-06",
                end_date="2014-12",
                is_current=False,
                description="Investment Banking Division",
            ),
        ],
        skills=["M&A", "Private Equity", "Financial Modeling"],
    )


@pytest.fixture
def consulting_profile():
    """A profile with consulting background."""
    return LinkedInProfile(
        profile_id="consulting-person",
        profile_url="https://linkedin.com/in/consulting-person",
        name="Elena Verdi",
        headline="Principal at Test Fund",
        location="Milan, Italy",
        connections=300,
        about="Former consultant now in PE",
        education=[
            Education(
                school="INSEAD",
                degree="MBA",
                field_of_study="Business Administration",
                start_year=2014,
                end_year=2015,
            ),
        ],
        experience=[
            Experience(
                company="Test Fund",
                title="Principal",
                location="Milan",
                start_date="2022-06",
                end_date=None,
                is_current=True,
                description=None,
            ),
            Experience(
                company="McKinsey & Company",
                title="Engagement Manager",
                location="Milan",
                start_date="2018-01",
                end_date="2022-05",
                is_current=False,
                description="Strategy consulting",
            ),
            Experience(
                company="Bain & Company",
                title="Consultant",
                location="Milan",
                start_date="2016-01",
                end_date="2017-12",
                is_current=False,
                description="Strategy consulting",
            ),
        ],
    )


class TestPostClassifier:
    """Tests for PostClassifier."""

    def test_classify_deal_announcement(self, deal_post):
        """Test classification of deal announcement."""
        classifier = PostClassifier()
        result = classifier.classify(deal_post)

        assert result.signal_type == SignalType.DEAL_ANNOUNCED
        assert result.confidence >= 0.8
        assert "TechCorp" in (result.extracted_entities.get("company_name") or "")

    def test_classify_exit_announcement(self, exit_post):
        """Test classification of exit announcement."""
        classifier = PostClassifier()
        result = classifier.classify(exit_post)

        assert result.signal_type == SignalType.EXIT_ANNOUNCED
        assert result.confidence >= 0.8

    def test_classify_fundraise_announcement(self, fundraise_post):
        """Test classification of fundraise announcement."""
        classifier = PostClassifier()
        result = classifier.classify(fundraise_post)

        assert result.signal_type == SignalType.FUNDRAISE_ANNOUNCED
        assert result.confidence >= 0.8
        assert result.extracted_entities.get("fund_number") == "IV"

    def test_classify_hire_announcement(self, hire_post):
        """Test classification of new hire announcement."""
        classifier = PostClassifier()
        result = classifier.classify(hire_post)

        assert result.signal_type == SignalType.PEOPLE_MOVE
        assert result.confidence >= 0.7

    def test_classify_generic_post(self, generic_post):
        """Test classification of generic post."""
        classifier = PostClassifier()
        result = classifier.classify(generic_post)

        assert result.signal_type == SignalType.UNKNOWN
        assert result.confidence < 0.5

    def test_classify_batch(self, deal_post, exit_post, generic_post):
        """Test batch classification with filtering."""
        classifier = PostClassifier(min_confidence=0.5)
        posts = [deal_post, exit_post, generic_post]

        results = classifier.classify_batch(posts, filter_unknown=True)

        # Should filter out generic post
        assert len(results) == 2
        assert all(r.signal_type != SignalType.UNKNOWN for r in results)

    def test_to_signal_records(self, deal_post):
        """Test conversion to signal records."""
        classifier = PostClassifier()
        classified = classifier.classify(deal_post)

        signals = classifier.to_signal_records([classified])

        assert len(signals) == 1
        signal = signals[0]
        assert signal["fund_slug"] == "test-fund"
        assert signal["signal_type"] == "deal_announced"
        assert signal["source_url"] is not None
        assert "observed_at" in signal


class TestProfileClassifier:
    """Tests for ProfileClassifier."""

    def test_classify_ib_background(self, ib_profile):
        """Test classification of IB background."""
        classifier = ProfileClassifier()
        result = classifier.classify(ib_profile)

        assert result.primary_background == BackgroundType.INVESTMENT_BANKING
        assert result.current_seniority == SeniorityLevel.PARTNER
        assert result.education_tier == "top_mba"
        assert result.estimated_gender == "male"

    def test_classify_consulting_background(self, consulting_profile):
        """Test classification of consulting background."""
        classifier = ProfileClassifier()
        result = classifier.classify(consulting_profile)

        assert result.primary_background == BackgroundType.CONSULTING
        assert result.current_seniority == SeniorityLevel.PRINCIPAL
        assert result.education_tier == "top_mba"
        assert result.estimated_gender == "female"

    def test_years_experience(self, ib_profile):
        """Test years of experience calculation."""
        classifier = ProfileClassifier()
        result = classifier.classify(ib_profile)

        # Started in 2012, so should have ~14 years
        assert result.years_experience is not None
        assert 10 <= result.years_experience <= 20

    def test_tenure_calculation(self, ib_profile):
        """Test tenure at current position calculation."""
        classifier = ProfileClassifier()
        result = classifier.classify(ib_profile)

        # Started in 2020, so ~6 years
        assert result.tenure_at_current is not None
        assert 4 <= result.tenure_at_current <= 8

    def test_background_summary(self, ib_profile, consulting_profile):
        """Test background summary generation."""
        classifier = ProfileClassifier()
        classified = classifier.classify_batch([ib_profile, consulting_profile])

        summary = classifier.get_background_summary(classified)

        assert summary["total_profiles"] == 2
        assert "investment_banking" in summary["backgrounds"]
        assert "consulting" in summary["backgrounds"]


class TestNormalization:
    """Tests for data normalization functions."""

    def test_normalize_post(self):
        """Test raw post normalization."""
        raw = {
            "urn": "urn:li:activity:12345",
            "text": "Test post content",
            "numLikes": 100,
            "numComments": 10,
            "postedAt": "2026-01-20T10:00:00Z",
            "url": "https://linkedin.com/posts/test",
        }

        post = normalize_post(raw, "test-fund", "Test Fund")

        assert post.post_id == "urn:li:activity:12345"
        assert post.text == "Test post content"
        assert post.engagement["likes"] == 100
        assert post.engagement["comments"] == 10
        assert post.published_at == "2026-01-20T10:00:00Z"

    def test_normalize_employee(self):
        """Test raw employee normalization."""
        raw = {
            "name": "Mario Rossi",
            "title": "Associate",
            "url": "https://linkedin.com/in/mario-rossi",
        }

        employee = normalize_employee(raw, "test-fund")

        assert employee.name == "Mario Rossi"
        assert employee.title == "Associate"
        assert employee.company_slug == "test-fund"
        assert employee.scraped_at is not None

    def test_normalize_profile(self):
        """Test raw profile normalization."""
        raw = {
            "publicIdentifier": "test-profile",
            "url": "https://linkedin.com/in/test-profile",
            "name": "Test Person",
            "headline": "Partner",
            "location": "Milan",
            "education": [
                {
                    "schoolName": "Bocconi",
                    "degreeName": "MBA",
                    "fieldOfStudy": "Finance",
                }
            ],
            "experience": [
                {
                    "companyName": "Test Fund",
                    "title": "Partner",
                    "isCurrent": True,
                }
            ],
        }

        profile = normalize_profile(raw, "test-fund")

        assert profile.profile_id == "test-profile"
        assert profile.name == "Test Person"
        assert len(profile.education) == 1
        assert len(profile.experience) == 1
        assert profile.company_slug == "test-fund"


class TestPeopleStats:
    """Tests for PeopleStatsCalculator."""

    def test_calculate_stats(self, ib_profile, consulting_profile):
        """Test stats calculation for a fund."""
        calculator = PeopleStatsCalculator()

        employees = [
            LinkedInEmployee("Person 1", "Partner", "url1", "test-fund", "2026-01-01"),
            LinkedInEmployee("Person 2", "Associate", "url2", "test-fund", "2026-01-01"),
            LinkedInEmployee("Person 3", "Analyst", "url3", "test-fund", "2026-01-01"),
        ]

        stats = calculator.calculate_stats(
            fund_slug="test-fund",
            fund_name="Test Fund",
            employees=employees,
            profiles=[ib_profile, consulting_profile],
        )

        assert stats.fund_slug == "test-fund"
        assert stats.total_employees == 3
        assert stats.background_ib >= 1
        assert stats.background_consulting >= 1
        assert stats.partners >= 1
        assert stats.principals >= 1

    def test_generate_summary(self, ib_profile):
        """Test summary report generation."""
        calculator = PeopleStatsCalculator()

        stats = calculator.calculate_stats(
            fund_slug="test-fund",
            fund_name="Test Fund",
            employees=[],
            profiles=[ib_profile],
        )

        summary = calculator.generate_summary_report([stats])

        assert summary["fund_count"] == 1
        assert "background_totals" in summary
        assert "seniority_totals" in summary


class TestHashtagExtraction:
    """Tests for hashtag and mention extraction."""

    def test_extract_hashtags(self):
        """Test hashtag extraction from post text."""
        from fundradar_worker.linkedin.posts_scraper import _extract_hashtags

        text = "Great news! #privateequity #investment #italy"
        hashtags = _extract_hashtags(text)

        assert len(hashtags) == 3
        assert "privateequity" in hashtags
        assert "investment" in hashtags
        assert "italy" in hashtags

    def test_extract_mentions(self):
        """Test mention extraction from post text."""
        from fundradar_worker.linkedin.posts_scraper import _extract_mentions

        text = "Congratulations to @[TechCorp Inc] and @[Mario Rossi] on the deal!"
        companies, people = _extract_mentions(text)

        assert "TechCorp Inc" in companies
        assert "Mario Rossi" in people
