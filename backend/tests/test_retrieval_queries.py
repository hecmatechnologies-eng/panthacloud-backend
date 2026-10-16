"""Tests for splitting one guest message into the separate questions it contains.

The behaviour these lock down came out of a real failure rather than a design exercise. A guest
emailed three questions in one message - room types and rates, check-out time, and whether there is
a pool - and the assistant answered the first two and then said it had no information about the
pool. The pool was documented. It had simply never been retrieved, because the message was embedded
as one vector and that vector landed in the room-types section.

These tests are about the splitting decision only. Whether the embeddings are any good is a
different question, and one that cannot be answered without calling a real provider - so the
end-to-end proof lives in ``test_knowledge_e2e.py`` and in manual verification.
"""

from app.core.config import settings
from app.runtime.chat import _query_variants


class TestSingleQuestion:
    def test_one_sentence_is_returned_unchanged(self) -> None:
        # The common case must not change. An extra split here would cost an embedding call per
        # turn for no gain, so this asserts equality and not merely containment.
        assert _query_variants("What room types do you have?") == ["What room types do you have?"]

    def test_sentence_without_question_mark_is_kept_whole(self) -> None:
        assert _query_variants("I need to know your cancellation policy") == [
            "I need to know your cancellation policy"
        ]

    def test_empty_message_yields_nothing(self) -> None:
        assert _query_variants("") == []
        assert _query_variants("   \n  ") == []


class TestMultipleQuestions:
    def test_two_sentences_become_two_queries(self) -> None:
        # Punctuation stays attached: the text given to the embedder should be what the guest wrote.
        # Splitting on a consuming delimiter deleted every question mark.
        assert _query_variants("What rooms do you have? Is there a pool?") == [
            "What rooms do you have?",
            "Is there a pool?",
        ]

    def test_newline_separated_questions_are_split(self) -> None:
        # Email guests use blank lines as list separators far more than punctuation.
        assert _query_variants("Room rates please\n\nCheck-out time\n\nPool?") == [
            "Room rates please",
            "Check-out time",
            "Pool?",
        ]

    def test_the_real_three_question_email_splits_into_three(self) -> None:
        # Verbatim from the message that exposed the bug, so the regression stays fixed. The
        # greeting and the sign-off drop out; each of the three questions survives as its own query.
        message = (
            "Hello,\n\n"
            "I would like to know about the available room types and their rates. Do you have a "
            "family room, and what does the deluxe king cost per night?\n\n"
            "Also, what time is check-out, and is there a swimming pool?\n\n"
            "Thank you,\nA guest"
        )
        assert _query_variants(message) == [
            "I would like to know about the available room types and their rates.",
            "Do you have a family room, and what does the deluxe king cost per night?",
            "Also, what time is check-out, and is there a swimming pool?",
        ]


class TestNonQuestions:
    def test_greeting_and_signoff_are_dropped(self) -> None:
        # Kept, they would return arbitrary passages that then compete for the merged result slots.
        assert _query_variants("Hello there, thanks!") == []

    def test_greeting_does_not_swallow_a_real_question(self) -> None:
        assert _query_variants("Hi, is there a gym?") == ["Hi, is there a gym?"]

    def test_pure_greeting_alone_retrieves_nothing(self) -> None:
        # Verified against the live system: a bare "Hey" searched the knowledge base and the
        # results were ranked by how much a greeting resembles the hotel's prose, not by relevance.
        assert _query_variants("Hey") == []
        assert _query_variants("Thank you so much") == []

    def test_repeated_question_is_searched_once(self) -> None:
        # Guests repeat themselves under pressure; a second identical search buys no new context.
        assert _query_variants("Do you have a pool? Do you have a pool?") == ["Do you have a pool?"]

    def test_bullet_markers_are_stripped(self) -> None:
        assert _query_variants("- Pool hours?\n- Gym hours?") == ["Pool hours?", "Gym hours?"]


class TestBounds:
    def test_query_count_is_capped(self) -> None:
        questions = " ".join(f"Question {n}?" for n in range(settings.RETRIEVAL_MAX_QUERIES + 5))
        assert len(_query_variants(questions)) == settings.RETRIEVAL_MAX_QUERIES

    def test_cap_is_honoured_without_reordering(self) -> None:
        # Order is preserved because the questions appear in the order the guest asked them, which
        # is the order the model reads them in.
        questions = " ".join(f"Item {n}?" for n in range(10))
        assert _query_variants(questions)[:3] == ["Item 0?", "Item 1?", "Item 2?"]