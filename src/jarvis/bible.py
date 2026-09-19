"""An offline Bible reference used by the ``bible`` skill.

The knowledge base follows the same shape as :mod:`jarvis.encyclopedia`:
entries are plain data, looked up by title, alias or reference, with a
forgiving fallback so small typos still resolve. Verse texts are quoted from
the World English Bible, which is in the public domain.

The data set is a hand-curated selection rather than the complete text of
scripture, so a question can always be answered with either a quotation, a
summary, or an honest "I do not have that passage".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Book:
    """A book of the Bible."""

    name: str
    testament: str
    division: str
    chapters: int
    summary: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass(frozen=True)
class Verse:
    """A single verse, quoted from the public domain World English Bible."""

    reference: str
    text: str

    @property
    def book(self) -> str:
        return self.reference.rsplit(" ", 1)[0]


@dataclass(frozen=True)
class Topic:
    """A theme of scripture with the passages that speak to it."""

    title: str
    summary: str
    references: Sequence[str] = field(default_factory=tuple)
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.title, *self.aliases)


BOOKS: Tuple[Book, ...] = (
    Book(
        name="Genesis",
        testament="Old Testament",
        division="Pentateuch",
        chapters=50,
        summary=(
            "Beginnings: creation, the fall, the flood, and the families of "
            "Abraham, Isaac, Jacob and Joseph."
        ),
        aliases=("gen",),
    ),
    Book(
        name="Exodus",
        testament="Old Testament",
        division="Pentateuch",
        chapters=40,
        summary=(
            "Israel's rescue from slavery in Egypt through Moses, the covenant "
            "at Sinai with the Ten Commandments, and the building of the "
            "tabernacle."
        ),
        aliases=("ex", "exod"),
    ),
    Book(
        name="Leviticus",
        testament="Old Testament",
        division="Pentateuch",
        chapters=27,
        summary="Laws of sacrifice, purity and holiness given to the priests.",
        aliases=("lev",),
    ),
    Book(
        name="Numbers",
        testament="Old Testament",
        division="Pentateuch",
        chapters=36,
        summary="Israel counted and tested through forty years in the wilderness.",
        aliases=("num",),
    ),
    Book(
        name="Deuteronomy",
        testament="Old Testament",
        division="Pentateuch",
        chapters=34,
        summary=(
            "Moses' farewell sermons restating the law before Israel enters the "
            "promised land."
        ),
        aliases=("deut", "deut."),
    ),
    Book(
        name="Joshua",
        testament="Old Testament",
        division="Historical books",
        chapters=24,
        summary="Entering and settling the promised land under Joshua.",
        aliases=("josh",),
    ),
    Book(
        name="Judges",
        testament="Old Testament",
        division="Historical books",
        chapters=21,
        summary="Cycles of rebellion and rescue through leaders such as Deborah and Gideon.",
        aliases=("judg",),
    ),
    Book(
        name="Ruth",
        testament="Old Testament",
        division="Historical books",
        chapters=4,
        summary="A Moabite widow's loyalty and her place in the family line of David.",
    ),
    Book(
        name="1 Samuel",
        testament="Old Testament",
        division="Historical books",
        chapters=31,
        summary="Samuel, Israel's first kings, and David's rise while Saul falls.",
        aliases=("first samuel", "1samuel", "1 sam", "i samuel"),
    ),
    Book(
        name="2 Samuel",
        testament="Old Testament",
        division="Historical books",
        chapters=24,
        summary="David's reign, his covenant with God, his sin and its consequences.",
        aliases=("second samuel", "2samuel", "2 sam", "ii samuel"),
    ),
    Book(
        name="1 Kings",
        testament="Old Testament",
        division="Historical books",
        chapters=22,
        summary="Solomon, the temple, and the kingdom divided after him.",
        aliases=("first kings", "1kings", "i kings"),
    ),
    Book(
        name="2 Kings",
        testament="Old Testament",
        division="Historical books",
        chapters=25,
        summary="The prophets Elijah and Elisha and the exile of both kingdoms.",
        aliases=("second kings", "2kings", "ii kings"),
    ),
    Book(
        name="1 Chronicles",
        testament="Old Testament",
        division="Historical books",
        chapters=29,
        summary="Israel's genealogies and David's reign retold for the returned exiles.",
        aliases=("first chronicles", "1chronicles", "1 chron", "i chronicles"),
    ),
    Book(
        name="2 Chronicles",
        testament="Old Testament",
        division="Historical books",
        chapters=36,
        summary="The temple, the kings of Judah, and the fall of Jerusalem.",
        aliases=("second chronicles", "2chronicles", "2 chron", "ii chronicles"),
    ),
    Book(
        name="Ezra",
        testament="Old Testament",
        division="Historical books",
        chapters=10,
        summary="Return from exile and the rebuilding of the temple.",
    ),
    Book(
        name="Nehemiah",
        testament="Old Testament",
        division="Historical books",
        chapters=13,
        summary="Rebuilding Jerusalem's walls and renewing the covenant.",
        aliases=("neh",),
    ),
    Book(
        name="Esther",
        testament="Old Testament",
        division="Historical books",
        chapters=10,
        summary="A Jewish queen in Persia risks her life to save her people.",
    ),
    Book(
        name="Job",
        testament="Old Testament",
        division="Wisdom and poetry",
        chapters=42,
        summary="A righteous man's suffering and the question of why the innocent suffer.",
    ),
    Book(
        name="Psalms",
        testament="Old Testament",
        division="Wisdom and poetry",
        chapters=150,
        summary="150 songs and prayers of praise, lament, thanksgiving and trust.",
        aliases=("psalm", "ps"),
    ),
    Book(
        name="Proverbs",
        testament="Old Testament",
        division="Wisdom and poetry",
        chapters=31,
        summary="Short sayings on wisdom, work, speech, money and the fear of the Lord.",
        aliases=("prov",),
    ),
    Book(
        name="Ecclesiastes",
        testament="Old Testament",
        division="Wisdom and poetry",
        chapters=12,
        summary="A search for meaning that ends in reverence and simple gifts.",
        aliases=("eccl", "qoheleth"),
    ),
    Book(
        name="Song of Solomon",
        testament="Old Testament",
        division="Wisdom and poetry",
        chapters=8,
        summary="Poetry celebrating love between a bride and her beloved.",
        aliases=("song of songs", "canticles"),
    ),
    Book(
        name="Isaiah",
        testament="Old Testament",
        division="Major prophets",
        chapters=66,
        summary="Judgement and comfort, and the servant who bears the sins of many.",
        aliases=("isa",),
    ),
    Book(
        name="Jeremiah",
        testament="Old Testament",
        division="Major prophets",
        chapters=52,
        summary="Warnings before Jerusalem's fall and the promise of a new covenant.",
        aliases=("jer",),
    ),
    Book(
        name="Lamentations",
        testament="Old Testament",
        division="Major prophets",
        chapters=5,
        summary="Grief over the ruined city, with mercies new every morning.",
        aliases=("lam",),
    ),
    Book(
        name="Ezekiel",
        testament="Old Testament",
        division="Major prophets",
        chapters=48,
        summary="Visions in exile, dry bones raised, and a restored temple.",
        aliases=("ezek",),
    ),
    Book(
        name="Daniel",
        testament="Old Testament",
        division="Major prophets",
        chapters=12,
        summary="Faithfulness in Babylon and visions of kingdoms that pass away.",
        aliases=("dan",),
    ),
    Book(
        name="Hosea",
        testament="Old Testament",
        division="Minor prophets",
        chapters=14,
        summary="God's steadfast love for an unfaithful people, pictured in a marriage.",
    ),
    Book(
        name="Joel",
        testament="Old Testament",
        division="Minor prophets",
        chapters=3,
        summary="Locusts, repentance, and the Spirit poured out on all flesh.",
    ),
    Book(
        name="Amos",
        testament="Old Testament",
        division="Minor prophets",
        chapters=9,
        summary="Justice rolling down like waters against comfortable injustice.",
    ),
    Book(
        name="Obadiah",
        testament="Old Testament",
        division="Minor prophets",
        chapters=1,
        summary="A single chapter against Edom's pride.",
        aliases=("obad",),
    ),
    Book(
        name="Jonah",
        testament="Old Testament",
        division="Minor prophets",
        chapters=4,
        summary="A reluctant prophet, a great fish, and mercy on Nineveh.",
    ),
    Book(
        name="Micah",
        testament="Old Testament",
        division="Minor prophets",
        chapters=7,
        summary="Do justly, love mercy, walk humbly with your God.",
    ),
    Book(
        name="Nahum",
        testament="Old Testament",
        division="Minor prophets",
        chapters=3,
        summary="The fall of Nineveh, a century after Jonah.",
    ),
    Book(
        name="Habakkuk",
        testament="Old Testament",
        division="Minor prophets",
        chapters=3,
        summary="Honest questions to God and a decision to rejoice anyway.",
        aliases=("hab",),
    ),
    Book(
        name="Zephaniah",
        testament="Old Testament",
        division="Minor prophets",
        chapters=3,
        summary="The day of the Lord, and God rejoicing over his people with singing.",
        aliases=("zeph",),
    ),
    Book(
        name="Haggai",
        testament="Old Testament",
        division="Minor prophets",
        chapters=2,
        summary="A call to finish rebuilding the temple.",
        aliases=("hag",),
    ),
    Book(
        name="Zechariah",
        testament="Old Testament",
        division="Minor prophets",
        chapters=14,
        summary="Night visions and promises of a humble coming king.",
        aliases=("zech",),
    ),
    Book(
        name="Malachi",
        testament="Old Testament",
        division="Minor prophets",
        chapters=4,
        summary="The last Old Testament word: worship offered honestly, and a messenger to come.",
        aliases=("mal",),
    ),
    Book(
        name="Matthew",
        testament="New Testament",
        division="Gospels",
        chapters=28,
        summary=(
            "Jesus as the promised king of Israel, including the Sermon on the "
            "Mount and the great commission."
        ),
        aliases=("matt", "gospel of matthew"),
    ),
    Book(
        name="Mark",
        testament="New Testament",
        division="Gospels",
        chapters=16,
        summary="The shortest, fastest moving gospel: Jesus the servant who acts.",
        aliases=("gospel of mark",),
    ),
    Book(
        name="Luke",
        testament="New Testament",
        division="Gospels",
        chapters=24,
        summary=(
            "An orderly account for Theophilus, with the parables of the good "
            "Samaritan and the prodigal son."
        ),
        aliases=("gospel of luke",),
    ),
    Book(
        name="John",
        testament="New Testament",
        division="Gospels",
        chapters=21,
        summary="Jesus as the eternal Word, written so that readers may believe.",
        aliases=("gospel of john",),
    ),
    Book(
        name="Acts",
        testament="New Testament",
        division="History",
        chapters=28,
        summary="The Spirit given at Pentecost and the church spreading to Rome.",
        aliases=("acts of the apostles",),
    ),
    Book(
        name="Romans",
        testament="New Testament",
        division="Letters of Paul",
        chapters=16,
        summary="Paul's fullest argument: sin, grace, faith and life in the Spirit.",
        aliases=("rom",),
    ),
    Book(
        name="1 Corinthians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=16,
        summary="Divisions, freedom, spiritual gifts, love and resurrection.",
        aliases=("first corinthians", "1corinthians", "1 cor", "i corinthians"),
    ),
    Book(
        name="2 Corinthians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=13,
        summary="Comfort in affliction and strength made perfect in weakness.",
        aliases=("second corinthians", "2corinthians", "2 cor", "ii corinthians"),
    ),
    Book(
        name="Galatians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=6,
        summary="Freedom from law-keeping and the fruit of the Spirit.",
        aliases=("gal",),
    ),
    Book(
        name="Ephesians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=6,
        summary="One new people in Christ, and the armour of God.",
        aliases=("eph",),
    ),
    Book(
        name="Philippians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=4,
        summary="Joy from prison, humility, and contentment in every circumstance.",
        aliases=("phil", "philippian"),
    ),
    Book(
        name="Colossians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=4,
        summary="The supremacy of Christ and a life clothed with compassion.",
        aliases=("col",),
    ),
    Book(
        name="1 Thessalonians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=5,
        summary="Encouragement to a young church and hope for those who have died.",
        aliases=("first thessalonians", "1thessalonians", "1 thess"),
    ),
    Book(
        name="2 Thessalonians",
        testament="New Testament",
        division="Letters of Paul",
        chapters=3,
        summary="Steadiness under pressure and honest work while waiting.",
        aliases=("second thessalonians", "2thessalonians", "2 thess"),
    ),
    Book(
        name="1 Timothy",
        testament="New Testament",
        division="Letters of Paul",
        chapters=6,
        summary="Pastoral instruction on teaching, leadership and money.",
        aliases=("first timothy", "1timothy", "1 tim"),
    ),
    Book(
        name="2 Timothy",
        testament="New Testament",
        division="Letters of Paul",
        chapters=4,
        summary="Paul's last letter: guard the faith, finish the race.",
        aliases=("second timothy", "2timothy", "2 tim"),
    ),
    Book(
        name="Titus",
        testament="New Testament",
        division="Letters of Paul",
        chapters=3,
        summary="Ordering the church on Crete and doing what is good.",
    ),
    Book(
        name="Philemon",
        testament="New Testament",
        division="Letters of Paul",
        chapters=1,
        summary="A personal appeal to receive a runaway slave as a brother.",
        aliases=("philem",),
    ),
    Book(
        name="Hebrews",
        testament="New Testament",
        division="General letters",
        chapters=13,
        summary="Christ greater than what came before, and a gallery of faith.",
        aliases=("heb",),
    ),
    Book(
        name="James",
        testament="New Testament",
        division="General letters",
        chapters=5,
        summary="Faith proved by action, the tongue, patience and prayer.",
    ),
    Book(
        name="1 Peter",
        testament="New Testament",
        division="General letters",
        chapters=5,
        summary="Hope and holiness for Christians suffering as strangers.",
        aliases=("first peter", "1peter", "1 pet"),
    ),
    Book(
        name="2 Peter",
        testament="New Testament",
        division="General letters",
        chapters=3,
        summary="Growth in grace and a warning about false teachers.",
        aliases=("second peter", "2peter", "2 pet"),
    ),
    Book(
        name="1 John",
        testament="New Testament",
        division="General letters",
        chapters=5,
        summary="God is light and God is love; walk in both.",
        aliases=("first john", "1john"),
    ),
    Book(
        name="2 John",
        testament="New Testament",
        division="General letters",
        chapters=1,
        summary="A short note on truth and love.",
        aliases=("second john", "2john"),
    ),
    Book(
        name="3 John",
        testament="New Testament",
        division="General letters",
        chapters=1,
        summary="A short note commending hospitality.",
        aliases=("third john", "3john"),
    ),
    Book(
        name="Jude",
        testament="New Testament",
        division="General letters",
        chapters=1,
        summary="Contend for the faith, and keep yourselves in God's love.",
    ),
    Book(
        name="Revelation",
        testament="New Testament",
        division="Prophecy",
        chapters=22,
        summary=(
            "Visions given to John: letters to seven churches, judgement, and a "
            "new heaven and a new earth."
        ),
        aliases=("rev", "apocalypse", "revelations"),
    ),
)


VERSES: Tuple[Verse, ...] = (
    Verse("Genesis 1:1", "In the beginning, God created the heavens and the earth."),
    Verse(
        "Genesis 1:27",
        "God created man in his own image. In God's image he created him; male "
        "and female he created them.",
    ),
    Verse(
        "Exodus 20:12",
        "Honor your father and your mother, that your days may be long in the "
        "land which Yahweh your God gives you.",
    ),
    Verse(
        "Deuteronomy 31:6",
        "Be strong and courageous. Don't be afraid or scared of them; for "
        "Yahweh your God himself is who goes with you. He will not fail you nor "
        "forsake you.",
    ),
    Verse(
        "Joshua 1:9",
        "Haven't I commanded you? Be strong and courageous. Don't be afraid. "
        "Don't be dismayed, for Yahweh your God is with you wherever you go.",
    ),
    Verse(
        "Psalms 23:1",
        "Yahweh is my shepherd; I shall lack nothing.",
    ),
    Verse(
        "Psalms 23:4",
        "Even though I walk through the valley of the shadow of death, I will "
        "fear no evil, for you are with me.",
    ),
    Verse(
        "Psalms 34:18",
        "Yahweh is near to those who have a broken heart, and saves those who "
        "have a crushed spirit.",
    ),
    Verse(
        "Psalms 46:1",
        "God is our refuge and strength, a very present help in trouble.",
    ),
    Verse(
        "Psalms 119:105",
        "Your word is a lamp to my feet, and a light for my path.",
    ),
    Verse(
        "Psalms 139:14",
        "I will give thanks to you, for I am fearfully and wonderfully made.",
    ),
    Verse(
        "Proverbs 3:5",
        "Trust in Yahweh with all your heart, and don't lean on your own "
        "understanding.",
    ),
    Verse(
        "Proverbs 17:17",
        "A friend loves at all times; and a brother is born for adversity.",
    ),
    Verse(
        "Ecclesiastes 3:1",
        "For everything there is a season, and a time for every purpose under "
        "heaven.",
    ),
    Verse(
        "Isaiah 40:31",
        "But those who wait for Yahweh will renew their strength. They will "
        "mount up with wings like eagles. They will run, and not be weary. They "
        "will walk, and not faint.",
    ),
    Verse(
        "Isaiah 41:10",
        "Don't you be afraid, for I am with you. Don't be dismayed, for I am "
        "your God. I will strengthen you. Yes, I will help you.",
    ),
    Verse(
        "Jeremiah 29:11",
        "For I know the thoughts that I think toward you, says Yahweh, thoughts "
        "of peace, and not of evil, to give you hope and a future.",
    ),
    Verse(
        "Lamentations 3:22",
        "It is because of Yahweh's loving kindnesses that we are not consumed, "
        "because his compassion doesn't fail.",
    ),
    Verse(
        "Micah 6:8",
        "He has shown you, O man, what is good. What does Yahweh require of "
        "you, but to act justly, to love mercy, and to walk humbly with your "
        "God?",
    ),
    Verse(
        "Matthew 5:9",
        "Blessed are the peacemakers, for they shall be called children of God.",
    ),
    Verse(
        "Matthew 6:34",
        "Therefore don't be anxious for tomorrow, for tomorrow will be anxious "
        "for itself. Each day's own evil is sufficient.",
    ),
    Verse(
        "Matthew 7:12",
        "Therefore whatever you desire for men to do to you, you shall also do "
        "to them; for this is the law and the prophets.",
    ),
    Verse(
        "Matthew 11:28",
        "Come to me, all you who labor and are heavily burdened, and I will "
        "give you rest.",
    ),
    Verse(
        "Matthew 22:37",
        "You shall love the Lord your God with all your heart, with all your "
        "soul, and with all your mind.",
    ),
    Verse(
        "Matthew 22:39",
        "A second likewise is this, 'You shall love your neighbor as yourself.'",
    ),
    Verse(
        "Mark 12:31",
        "There is no other commandment greater than these.",
    ),
    Verse(
        "Luke 6:31",
        "As you would like people to do to you, do exactly so to them.",
    ),
    Verse(
        "John 1:1",
        "In the beginning was the Word, and the Word was with God, and the Word "
        "was God.",
    ),
    Verse(
        "John 3:16",
        "For God so loved the world, that he gave his one and only Son, that "
        "whoever believes in him should not perish, but have eternal life.",
    ),
    Verse(
        "John 14:6",
        "Jesus said to him, \"I am the way, the truth, and the life. No one "
        "comes to the Father, except through me.\"",
    ),
    Verse(
        "John 14:27",
        "Peace I leave with you. My peace I give to you; not as the world "
        "gives, I give to you. Don't let your heart be troubled, neither let it "
        "be fearful.",
    ),
    Verse(
        "Romans 8:28",
        "We know that all things work together for good for those who love God, "
        "for those who are called according to his purpose.",
    ),
    Verse(
        "Romans 8:38",
        "For I am persuaded that neither death, nor life, nor angels, nor "
        "principalities, nor things present, nor things to come, nor powers, "
        "nor height, nor depth, nor any other created thing will be able to "
        "separate us from God's love.",
    ),
    Verse(
        "Romans 12:2",
        "Don't be conformed to this world, but be transformed by the renewing "
        "of your mind.",
    ),
    Verse(
        "1 Corinthians 13:4",
        "Love is patient and is kind. Love doesn't envy. Love doesn't brag, is "
        "not proud.",
    ),
    Verse(
        "1 Corinthians 13:13",
        "But now faith, hope, and love remain, these three. The greatest of "
        "these is love.",
    ),
    Verse(
        "Galatians 5:22",
        "But the fruit of the Spirit is love, joy, peace, patience, kindness, "
        "goodness, faith, gentleness, and self-control.",
    ),
    Verse(
        "Ephesians 2:8",
        "For by grace you have been saved through faith, and that not of "
        "yourselves; it is the gift of God.",
    ),
    Verse(
        "Ephesians 4:32",
        "And be kind to one another, tender hearted, forgiving each other, just "
        "as God also in Christ forgave you.",
    ),
    Verse(
        "Philippians 4:6",
        "In nothing be anxious, but in everything, by prayer and petition with "
        "thanksgiving, let your requests be made known to God.",
    ),
    Verse(
        "Philippians 4:13",
        "I can do all things through Christ, who strengthens me.",
    ),
    Verse(
        "Colossians 3:13",
        "Bearing with one another, and forgiving each other, if any man has a "
        "complaint against any; even as Christ forgave you, so you also do.",
    ),
    Verse(
        "Hebrews 11:1",
        "Now faith is assurance of things hoped for, proof of things not seen.",
    ),
    Verse(
        "James 1:5",
        "But if any of you lacks wisdom, let him ask of God, who gives to all "
        "liberally and without reproach, and it will be given to him.",
    ),
    Verse(
        "1 Peter 5:7",
        "Casting all your worries on him, because he cares for you.",
    ),
    Verse(
        "1 John 4:8",
        "He who doesn't love doesn't know God, for God is love.",
    ),
    Verse(
        "Revelation 21:4",
        "He will wipe away every tear from their eyes. Death will be no more; "
        "neither will there be mourning, nor crying, nor pain any more.",
    ),
)


TOPICS: Tuple[Topic, ...] = (
    Topic(
        title="The Bible",
        summary=(
            "The Bible is a library of 66 books written over roughly a "
            "millennium and a half: 39 in the Old Testament, shared with the "
            "Hebrew scriptures, and 27 in the New Testament. It gathers law, "
            "history, poetry, prophecy, gospels and letters, and Jewish and "
            "Christian communities read it as scripture."
        ),
        references=("Psalms 119:105", "2 Timothy 3:16"),
        aliases=("scripture", "holy bible", "the scriptures", "what is the bible"),
    ),
    Topic(
        title="Love",
        summary=(
            "Love is the command Jesus called greatest: love God wholly and "
            "your neighbour as yourself. Paul describes it as patient and kind "
            "rather than a feeling, and John says simply that God is love."
        ),
        references=(
            "Matthew 22:37",
            "Matthew 22:39",
            "1 Corinthians 13:4",
            "1 Corinthians 13:13",
            "1 John 4:8",
        ),
        aliases=("loving others", "charity", "greatest commandment", "agape"),
    ),
    Topic(
        title="Fear and courage",
        summary=(
            "Scripture meets fear with presence rather than argument: the "
            "repeated promise is not that nothing will go wrong but that God "
            "goes with you."
        ),
        references=("Joshua 1:9", "Isaiah 41:10", "Psalms 23:4", "Deuteronomy 31:6"),
        aliases=("fear", "courage", "afraid", "being afraid", "bravery"),
    ),
    Topic(
        title="Anxiety and worry",
        summary=(
            "The Bible answers worry with prayer, one day at a time, and with "
            "the invitation to hand the weight over rather than carry it."
        ),
        references=("Philippians 4:6", "Matthew 6:34", "1 Peter 5:7", "John 14:27"),
        aliases=("anxiety", "worry", "stress", "anxious", "worried"),
    ),
    Topic(
        title="Grief and comfort",
        summary=(
            "Lament is part of scripture, not a failure of faith. The Psalms "
            "sit with the broken hearted, Lamentations finds mercy new every "
            "morning, and Revelation ends with tears wiped away."
        ),
        references=("Psalms 34:18", "Lamentations 3:22", "Revelation 21:4", "Matthew 11:28"),
        aliases=("grief", "comfort", "mourning", "sorrow", "sadness", "loss"),
    ),
    Topic(
        title="Forgiveness",
        summary=(
            "Forgiveness in the Bible is both received and given: those forgiven "
            "are told to forgive in the same measure."
        ),
        references=("Colossians 3:13", "Ephesians 4:32", "Matthew 6:14"),
        aliases=("forgiving", "forgive", "mercy"),
    ),
    Topic(
        title="Faith",
        summary=(
            "Faith is described as assurance of what is hoped for and proof of "
            "what is not seen, and as trust that does not depend on having "
            "understood everything."
        ),
        references=("Hebrews 11:1", "Proverbs 3:5", "Ephesians 2:8"),
        aliases=("belief", "believing", "trust", "trusting God"),
    ),
    Topic(
        title="Hope",
        summary=(
            "Hope in scripture is expectation grounded in God's character: "
            "strength renewed for those who wait, and a future promised to "
            "people in exile."
        ),
        references=("Jeremiah 29:11", "Isaiah 40:31", "Romans 8:28"),
        aliases=("hopeful", "hopelessness", "future"),
    ),
    Topic(
        title="Peace",
        summary=(
            "Peace is both an inner gift Jesus leaves with his followers and "
            "work to be done: peacemakers are called children of God."
        ),
        references=("John 14:27", "Matthew 5:9", "Philippians 4:6"),
        aliases=("peacemaking", "calm", "shalom"),
    ),
    Topic(
        title="Wisdom",
        summary=(
            "Wisdom literature teaches practical skill for living, and James "
            "adds that anyone short of it may simply ask God for more."
        ),
        references=("James 1:5", "Proverbs 3:5", "Ecclesiastes 3:1"),
        aliases=("wise", "guidance", "decisions", "discernment"),
    ),
    Topic(
        title="Justice",
        summary=(
            "The prophets tie worship to justice: what God requires is to act "
            "justly, love mercy and walk humbly."
        ),
        references=("Micah 6:8", "Amos 5:24", "Isaiah 1:17"),
        aliases=("injustice", "the poor", "oppression", "fairness"),
    ),
    Topic(
        title="Prayer",
        summary=(
            "Prayer runs from the Lord's Prayer to the Psalms' complaints. "
            "Paul's rule is simple: be anxious for nothing, but pray about "
            "everything, with thanksgiving."
        ),
        references=("Matthew 6:9", "Philippians 4:6", "James 5:16"),
        aliases=("praying", "how to pray"),
    ),
    Topic(
        title="The Ten Commandments",
        summary=(
            "Given at Sinai in Exodus 20 and repeated in Deuteronomy 5: worship "
            "God alone, no idols, do not misuse his name, keep the Sabbath, "
            "honour your parents, do not murder, commit adultery, steal, give "
            "false testimony or covet."
        ),
        references=("Exodus 20:1", "Exodus 20:12", "Deuteronomy 5:6"),
        aliases=("ten commandments", "commandments", "decalogue", "the law"),
    ),
    Topic(
        title="Jesus",
        summary=(
            "Jesus of Nazareth is the centre of the New Testament: born in "
            "Bethlehem, teaching and healing in Galilee, crucified in Jerusalem "
            "and, the gospels say, raised on the third day. Christians confess "
            "him as the Word made flesh."
        ),
        references=("John 1:1", "John 3:16", "John 14:6"),
        aliases=("jesus christ", "christ", "the messiah", "son of god"),
    ),
    Topic(
        title="Creation",
        summary=(
            "Genesis opens with God creating the heavens and the earth and "
            "making humanity in his own image, a claim about dignity as much as "
            "about origins."
        ),
        references=("Genesis 1:1", "Genesis 1:27", "Psalms 139:14"),
        aliases=("creation story", "genesis creation", "beginning"),
    ),
    Topic(
        title="Work and rest",
        summary=(
            "Scripture dignifies work and commands rest: the Sabbath is built "
            "into the commandments, and Jesus invites the weary to come to him "
            "for rest."
        ),
        references=("Exodus 20:12", "Matthew 11:28", "Ecclesiastes 3:1"),
        aliases=("work", "rest", "sabbath", "burnout"),
    ),
    Topic(
        title="Money",
        summary=(
            "The Bible treats money as a servant and a rival: it warns against "
            "the love of money, commends generosity, and says no one can serve "
            "both God and wealth."
        ),
        references=("Matthew 6:24", "1 Timothy 6:10", "Proverbs 3:9"),
        aliases=("wealth", "riches", "greed", "generosity"),
    ),
    Topic(
        title="Moses",
        summary=(
            "Moses is the prophet who led Israel out of slavery in Egypt, "
            "received the law at Sinai and guided the people through forty "
            "years in the wilderness. His story runs from Exodus to "
            "Deuteronomy."
        ),
        references=("Exodus 20:12", "Deuteronomy 31:6"),
        aliases=("prophet moses",),
    ),
    Topic(
        title="David",
        summary=(
            "David is the shepherd who became Israel's second king: he faced "
            "Goliath, is credited with many of the Psalms, and is remembered "
            "both for his devotion and for his failures."
        ),
        references=("Psalms 23:1", "Psalms 23:4", "Psalms 51:10"),
        aliases=("king david",),
    ),
    Topic(
        title="Paul",
        summary=(
            "Paul of Tarsus persecuted the early church, met Christ on the road "
            "to Damascus, and became its most travelled missionary. Thirteen "
            "New Testament letters carry his name."
        ),
        references=("Romans 8:28", "Philippians 4:13", "1 Corinthians 13:13"),
        aliases=("apostle paul", "saint paul", "saul of tarsus"),
    ),
    Topic(
        title="Friendship",
        summary=(
            "Proverbs says a friend loves at all times, and Jesus calls his "
            "followers friends rather than servants."
        ),
        references=("Proverbs 17:17", "John 15:13", "Ecclesiastes 4:9"),
        aliases=("friends", "friend"),
    ),
)


_BOOK_ORDER: Dict[str, int] = {book.name: index for index, book in enumerate(BOOKS)}

_REFERENCE_RE = re.compile(
    r"^(?P<book>.+?)\s+(?P<chapter>\d+)\s*[:.\s]\s*(?P<verse>\d+)$"
)


def _normalise(text: str) -> str:
    """Return a comparable form of ``text`` for lookups."""

    cleaned = (text or "").strip().lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^\w\s:]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned)
    cleaned = re.sub(r"^(?:1st|first|i)\s+", "1 ", cleaned)
    cleaned = re.sub(r"^(?:2nd|second|ii)\s+", "2 ", cleaned)
    cleaned = re.sub(r"^(?:3rd|third|iii)\s+", "3 ", cleaned)
    cleaned = re.sub(r"^(\d)\s*", r"\1 ", cleaned)
    return cleaned


def _build_book_index() -> Dict[str, Book]:
    index: Dict[str, Book] = {}
    for book in BOOKS:
        for key in book.keys:
            index.setdefault(_normalise(key), book)
    return index


def _build_topic_index() -> Dict[str, Topic]:
    index: Dict[str, Topic] = {}
    for topic in TOPICS:
        for key in topic.keys:
            index.setdefault(_normalise(key), topic)
    return index


_BOOK_INDEX: Dict[str, Book] = _build_book_index()
_TOPIC_INDEX: Dict[str, Topic] = _build_topic_index()
_VERSE_INDEX: Dict[str, Verse] = {
    _normalise(verse.reference): verse for verse in VERSES
}


def books() -> List[str]:
    """Return the book names in canonical order."""

    return [book.name for book in BOOKS]


def topics() -> List[str]:
    """Return the topic titles, alphabetically."""

    return sorted(topic.title for topic in TOPICS)


def find_book(query: str) -> Optional[Book]:
    """Return the book matching ``query``, or ``None``.

    Matching ignores case and punctuation, understands aliases and numbered
    forms such as ``first John``, and tolerates small typos.
    """

    key = _normalise(query)
    if not key:
        return None
    book = _BOOK_INDEX.get(key)
    if book is not None:
        return book
    key = re.sub(r"^(?:book of|the book of|gospel of)\s+", "", key)
    book = _BOOK_INDEX.get(key)
    if book is not None:
        return book
    close = get_close_matches(key, list(_BOOK_INDEX), n=1, cutoff=0.85)
    if close:
        return _BOOK_INDEX[close[0]]
    return None


def parse_reference(query: str) -> Optional[str]:
    """Return a canonical ``Book chapter:verse`` reference, or ``None``."""

    text = (query or "").strip().rstrip(".?!")
    text = re.sub(r"\s+", " ", text)
    match = _REFERENCE_RE.match(text)
    if match is None:
        return None
    book = find_book(match.group("book"))
    if book is None:
        return None
    chapter = int(match.group("chapter"))
    if chapter < 1 or chapter > book.chapters:
        return None
    verse = int(match.group("verse"))
    if verse < 1:
        return None
    return f"{book.name} {chapter}:{verse}"


def find_verse(query: str) -> Optional[Verse]:
    """Return the verse for a reference such as ``John 3:16``, or ``None``."""

    reference = parse_reference(query)
    if reference is None:
        return None
    return _VERSE_INDEX.get(_normalise(reference))


def find_topic(query: str) -> Optional[Topic]:
    """Return the topic matching ``query``, or ``None``."""

    key = _normalise(query)
    if not key:
        return None
    topic = _TOPIC_INDEX.get(key)
    if topic is not None:
        return topic
    if key.endswith("s") and len(key) > 3:
        topic = _TOPIC_INDEX.get(key[:-1])
        if topic is not None:
            return topic
    close = get_close_matches(key, list(_TOPIC_INDEX), n=1, cutoff=0.85)
    if close:
        return _TOPIC_INDEX[close[0]]
    return None


def verses_for(topic: Topic) -> List[Verse]:
    """Return the quoted verses a topic points at, in canonical order."""

    found = [
        _VERSE_INDEX[_normalise(reference)]
        for reference in topic.references
        if _normalise(reference) in _VERSE_INDEX
    ]
    return sorted(found, key=_verse_sort_key)


def search(query: str, limit: int = 3) -> List[Verse]:
    """Return verses whose text mentions the words in ``query``."""

    words = [
        word
        for word in re.findall(r"[a-z']+", (query or "").lower())
        if len(word) > 2 and word not in _SEARCH_STOPWORDS
    ]
    if not words:
        return []
    scored: List[Tuple[int, Tuple[int, int], Verse]] = []
    for verse in VERSES:
        haystack = verse.text.lower()
        score = sum(1 for word in words if word in haystack)
        if score:
            scored.append((-score, _verse_sort_key(verse), verse))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [verse for _, _, verse in scored[:limit]]


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Return topic titles that look similar to ``query``."""

    key = _normalise(query)
    if not key:
        return []
    matches = get_close_matches(key, list(_TOPIC_INDEX), n=limit * 2, cutoff=0.68)
    titles: List[str] = []
    for match in matches:
        title = _TOPIC_INDEX[match].title
        if title not in titles:
            titles.append(title)
        if len(titles) == limit:
            break
    return titles


def describe_book(book: Book) -> str:
    """Return a sentence describing ``book``."""

    chapters = "1 chapter" if book.chapters == 1 else f"{book.chapters} chapters"
    return (
        f"{book.name} is a book of the {book.testament} ({book.division}), "
        f"{chapters}. {book.summary}"
    )


def describe_topic(topic: Topic) -> str:
    """Return the topic summary followed by the passages it quotes."""

    lines = [f"{topic.title}: {topic.summary}"]
    quoted = verses_for(topic)
    for verse in quoted:
        lines.append(f"- {verse.reference}: {verse.text}")
    unquoted = [
        reference
        for reference in topic.references
        if _normalise(reference) not in _VERSE_INDEX
    ]
    if unquoted:
        lines.append("See also: " + ", ".join(unquoted) + ".")
    return "\n".join(lines)


def _verse_sort_key(verse: Verse) -> Tuple[int, int]:
    book_index = _BOOK_ORDER.get(verse.book, len(BOOKS))
    chapter = int(verse.reference.rsplit(" ", 1)[1].split(":")[0])
    return (book_index, chapter)


_SEARCH_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "you",
        "your",
        "his",
        "her",
        "their",
        "with",
        "that",
        "this",
        "what",
        "does",
        "say",
        "says",
        "about",
        "bible",
        "verse",
        "verses",
        "passage",
        "scripture",
        "tell",
        "have",
        "there",
        "from",
        "them",
        "who",
        "was",
        "were",
        "are",
        "when",
        "where",
        "how",
        "did",
        "its",
        "one",
        "any",
        "all",
        "not",
    }
)
