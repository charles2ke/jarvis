import os
import subprocess
import unittest
from unittest import mock

from jarvis import emergency
from jarvis.assistant import Assistant
from jarvis.memory import Memory
from jarvis.skills import _emergency_call, _emergency_share, _emergency_text

UN_MEMBERS_SAMPLE = (
    "Kenya", "Japan", "Brazil", "Germany", "India", "Australia", "Nigeria",
    "Tuvalu", "Bhutan", "Saint Lucia", "Vanuatu", "Eswatini", "North Korea",
)


class EmergencyDataTests(unittest.TestCase):
    def test_lookup_by_name_and_alias(self):
        self.assertEqual(emergency.find("usa").country, "United States")
        self.assertEqual(emergency.find("the UK").country, "United Kingdom")
        self.assertEqual(emergency.find("Ivory Coast").country, "Côte d'Ivoire")
        self.assertEqual(emergency.find("DRC").country, "Democratic Republic of the Congo")
        self.assertIsNone(emergency.find("Narnia"))
        self.assertIsNone(emergency.find(""))

    def test_every_un_member_sample_and_numbers_are_dialable(self):
        for name in UN_MEMBERS_SAMPLE:
            self.assertIsNotNone(emergency.find(name), name)
        self.assertGreaterEqual(len(emergency.countries()), 193)
        self.assertEqual(len(set(emergency.countries())), len(emergency.NUMBERS))
        for entry in emergency.NUMBERS:
            self.assertTrue(entry.main_number(), entry.country)
            for service in emergency.SERVICES:
                value = getattr(entry, service)
                if value:
                    emergency.dial_digits(value)

    def test_known_numbers(self):
        self.assertEqual(emergency.find("United States").number_for("police"), "911")
        self.assertEqual(emergency.find("United Kingdom").main_number(), "999")
        self.assertEqual(emergency.find("Japan").number_for("ambulance"), "119")
        self.assertEqual(emergency.find("Japan").number_for("police"), "110")
        self.assertEqual(emergency.find("Germany").main_number(), "112")
        self.assertEqual(emergency.find("Australia").main_number(), "000")
        self.assertEqual(emergency.find("France").number_for("paramedics"), "15")

    def test_missing_service_falls_back_to_main_number(self):
        self.assertEqual(emergency.find("Namibia").number_for("ambulance"), "112")

    def test_estonia_uses_112_for_all_services(self):
        entry = emergency.find("Estonia")
        for service in emergency.SERVICES:
            with self.subTest(service=service):
                self.assertEqual(getattr(entry, service), "112")
                self.assertEqual(entry.number_for(service), "112")

    def test_verified_sms_destinations(self):
        for country, sms in emergency.SMS_DESTINATIONS.items():
            with self.subTest(country=country):
                self.assertIsNotNone(emergency.find(country))
                self.assertEqual(emergency.dial_digits(sms.number), sms.number)
                self.assertTrue(sms.requirements)
                self.assertTrue(sms.source.startswith("https://"))
        self.assertEqual(emergency.SMS_DESTINATIONS["France"].number, "114")
        self.assertEqual(emergency.find("France").number_for("police"), "17")

    def test_links(self):
        self.assertEqual(emergency.tel_link("10 111"), "tel:10111")
        self.assertEqual(emergency.tel_link("+254 700-000-000"), "tel:+254700000000")
        self.assertEqual(emergency.sms_link("911", "help & hurry"), "sms:911?body=help%20%26%20hurry")
        self.assertEqual(
            emergency.mailto_link("me@example.com", "Hi there", "a&b"),
            "mailto:me@example.com?subject=Hi%20there&body=a%26b",
        )
        with self.assertRaises(emergency.EmergencyError):
            emergency.tel_link("no digits")
        with self.assertRaises(emergency.EmergencyError):
            emergency.tel_link("1" * 16)
        with self.assertRaises(emergency.EmergencyError):
            emergency.mailto_link("me@example.com\r\nBcc: x@y.com")
        with self.assertRaises(emergency.EmergencyError):
            emergency.mailto_link("not-an-email")

    def test_handoff_is_opt_in(self):
        opener = mock.Mock()
        reply = emergency.handoff("tel:112", opener=opener, environ={})
        opener.assert_not_called()
        self.assertIn("JARVIS_DIAL_ENABLED", reply)
        reply = emergency.handoff(
            "tel:112", opener=opener, environ={"JARVIS_DIAL_ENABLED": "1"}
        )
        opener.assert_called_once_with("tel:112")
        self.assertIn("I opened tel:112", reply)

    def test_opener_command(self):
        self.assertEqual(emergency.opener_command({}, "linux"), ["xdg-open"])
        self.assertEqual(emergency.opener_command({}, "darwin"), ["open"])
        self.assertEqual(
            emergency.opener_command({}, "win32"), ["rundll32", "url.dll,FileProtocolHandler"]
        )
        self.assertEqual(
            emergency.opener_command({"JARVIS_DIAL_COMMAND": "kdeconnect-cli --share"}),
            ["kdeconnect-cli", "--share"],
        )

    def test_open_link_rejects_other_schemes_and_reports_errors(self):
        with self.assertRaises(emergency.EmergencyError):
            emergency.open_link("https://example.com")
        with mock.patch.object(emergency.subprocess, "run") as run:
            emergency.open_link("tel:112")
            self.assertEqual(run.call_args[0][0][-1], "tel:112")
        with mock.patch.object(
            emergency.subprocess, "run", side_effect=FileNotFoundError("xdg-open")
        ):
            with self.assertRaises(emergency.EmergencyError):
                emergency.open_link("tel:112")
        with mock.patch.object(
            emergency.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, "xdg-open", stderr="no handler"),
        ):
            with self.assertRaisesRegex(emergency.EmergencyError, "no handler"):
                emergency.open_link("tel:112")


class EmergencySkillTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("JARVIS_DIAL_ENABLED", None)
        self.assistant = Assistant(memory=Memory(None))

    def skill_for(self, text):
        return self.assistant.registry.resolve(text)[0].name

    def test_routing(self):
        self.assertEqual(self.skill_for("what are the emergency numbers in Japan?"), "emergency-numbers")
        self.assertEqual(self.skill_for("police number in France"), "emergency-numbers")
        self.assertEqual(self.skill_for("what do I dial for an ambulance in India?"), "emergency-numbers")
        self.assertEqual(self.skill_for("call the police in Kenya"), "emergency-call")
        self.assertEqual(self.skill_for("please dial an ambulance"), "emergency-call")
        self.assertEqual(self.skill_for("text the police in the US: help"), "emergency-text")
        self.assertEqual(
            self.skill_for("email the emergency numbers for Kenya to me@example.com"),
            "emergency-share",
        )
        self.assertEqual(
            self.skill_for("dm the emergency numbers for Kenya to +254 700 000 000"),
            "emergency-share",
        )

    def test_does_not_steal_other_skills(self):
        self.assertEqual(self.skill_for("I want to kill myself, call the police"), "crisis-support")
        self.assertNotIn("emergency", self.skill_for("emergency fund on 1800 a month of essentials"))
        self.assertNotIn("emergency", self.skill_for("what is an EPIRB?"))

    def test_lookup_replies(self):
        reply = self.assistant.respond("emergency numbers in Japan")
        self.assertIn("police 110, ambulance 119, fire 119", reply)
        self.assertIn("call the police in Japan", reply)
        reply = self.assistant.respond("emergency number for the UK")
        self.assertIn("dial 999 for police, ambulance and fire", reply)
        self.assertIn("The ambulance number in India is 108.", self.assistant.respond("ambulance number in India"))
        self.assertIn("no single national ambulance number", self.assistant.respond("ambulance number in Namibia"))
        self.assertIn("I do not have emergency numbers for 'Narnia'", self.assistant.respond("emergency numbers in Narnia"))
        self.assertIn("112", self.assistant.respond("emergency numbers"))
        self.assertIn("Zimbabwe", self.assistant.respond("list emergency countries"))

    def test_call_without_opt_in_only_shows_link(self):
        reply = self.assistant.respond("call the police in Kenya")
        self.assertIn("Dial 999 for police in Kenya", reply)
        self.assertIn("tel:999", reply)
        self.assertIn("JARVIS_DIAL_ENABLED", reply)
        self.assertIn(emergency.DISCLAIMER, reply)
        self.assertIn("Which country", self.assistant.respond("call an ambulance"))

    def test_call_with_opt_in_opens_tel_link(self):
        opener = mock.Mock()
        match = self.assistant.registry.resolve("call the fire brigade in Germany")[1]
        reply = _emergency_call(
            match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": "yes"}
        )
        opener.assert_called_once_with("tel:112")
        self.assertIn("I opened tel:112", reply)
        self.assertIn(emergency.DISCLAIMER, reply)

    def test_call_missing_service_identifies_fallback(self):
        for enabled in ("0", "1"):
            with self.subTest(enabled=enabled):
                opener = mock.Mock()
                match = self.assistant.registry.resolve("call the fire service in Libya")[1]
                reply = _emergency_call(
                    match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": enabled}
                )
                self.assertIn("no single national fire number", reply)
                self.assertIn("dial 1515 as a fallback", reply)
                self.assertIn("ask the operator for the fire", reply)
                self.assertNotIn("Dial 1515 for fire", reply)
                self.assertIn(emergency.DISCLAIMER, reply)
                if enabled == "1":
                    opener.assert_called_once_with("tel:1515")
                else:
                    opener.assert_not_called()
                    self.assertIn("tel:1515", reply)

    def test_call_police_in_estonia_uses_112(self):
        opener = mock.Mock()
        match = self.assistant.registry.resolve("call the police in Estonia")[1]
        reply = _emergency_call(
            match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": "1"}
        )
        opener.assert_called_once_with("tel:112")
        self.assertIn("Dial 112 for police in Estonia", reply)

    def test_call_reports_opener_errors(self):
        opener = mock.Mock(side_effect=emergency.EmergencyError("boom"))
        match = self.assistant.registry.resolve("call the police in Japan")[1]
        reply = _emergency_call(match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": "1"})
        self.assertIn("Dial 110", reply)
        self.assertIn("could not open your phone app: boom", reply)
        self.assertIn(emergency.DISCLAIMER, reply)

    def test_text_emergency_services(self):
        opener = mock.Mock()
        match = self.assistant.registry.resolve(
            "text the police in France: there is a break-in"
        )[1]
        reply = _emergency_text(match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": "1"})
        opener.assert_called_once_with("sms:114?body=there%20is%20a%20break-in")
        self.assertIn("difficulty hearing or speaking", reply)
        self.assertIn("unsafe to speak aloud", reply)
        self.assertIn("call 17 instead", reply)
        self.assertIn(emergency.DISCLAIMER, reply)
        default = self.assistant.respond("sms emergency services in UK")
        self.assertIn("sms:999?body=Emergency%3A%20I%20need%20help", default)
        self.assertIn("deaf, hard of hearing", default)
        self.assertIn("register your mobile first", default)
        self.assertIn("registration confirmation", default)
        self.assertIn("call 999 instead", default)
        self.assertIn(emergency.DISCLAIMER, default)

    def test_text_uses_verified_destination_for_each_service(self):
        for service, voice_number in (("police", "17"), ("ambulance", "15"), ("fire", "18")):
            with self.subTest(service=service):
                reply = self.assistant.respond(f"text the {service} in France: help & hurry")
                self.assertIn("sms:114?body=help%20%26%20hurry", reply)
                self.assertNotIn(f"sms:{voice_number}?", reply)
                self.assertIn(f"call {voice_number} instead", reply)
                self.assertIn(emergency.DISCLAIMER, reply)

    def test_text_declines_unverified_destinations(self):
        for country, number in (("US", "911"), ("Japan", "110"), ("Kenya", "999")):
            for enabled in ("0", "1"):
                with self.subTest(country=country, enabled=enabled):
                    opener = mock.Mock()
                    match = self.assistant.registry.resolve(f"text the police in {country}: help")[1]
                    reply = _emergency_text(
                        match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": enabled}
                    )
                    opener.assert_not_called()
                    self.assertIn("cannot prepare an emergency text", reply)
                    self.assertNotIn("sms:", reply)
                    self.assertIn(f"call {number} instead", reply)
                    self.assertIn(emergency.DISCLAIMER, reply)

    def test_text_reports_opener_errors_with_warning(self):
        opener = mock.Mock(side_effect=emergency.EmergencyError("boom"))
        match = self.assistant.registry.resolve("text the police in France: help")[1]
        reply = _emergency_text(
            match, None, opener=opener, environ={"JARVIS_DIAL_ENABLED": "1"}
        )
        opener.assert_called_once_with("sms:114?body=help")
        self.assertIn("could not open your messages app: boom", reply)
        self.assertIn("difficulty hearing or speaking", reply)
        self.assertIn("call 17 instead", reply)
        self.assertIn(emergency.DISCLAIMER, reply)

    def test_share_by_email_and_text(self):
        opener = mock.Mock()
        env = {"JARVIS_DIAL_ENABLED": "1"}
        match = self.assistant.registry.resolve(
            "email the emergency numbers for Kenya to me@example.com."
        )[1]
        reply = _emergency_share(match, None, opener=opener, environ=env)
        link = opener.call_args[0][0]
        self.assertTrue(link.startswith("mailto:me@example.com?subject=Emergency%20numbers%20for%20Kenya"))
        self.assertIn("999", link)
        self.assertIn("an email to me@example.com", reply)

        opener.reset_mock()
        match = self.assistant.registry.resolve(
            "text the emergency numbers for Japan to +81 90 1234 5678"
        )[1]
        reply = _emergency_share(match, None, opener=opener, environ=env)
        self.assertTrue(opener.call_args[0][0].startswith("sms:+819012345678?body="))
        self.assertIn("a text message to +819012345678", reply)

    def test_share_rejects_mismatched_recipients(self):
        self.assertIn(
            "does not look like an email address",
            self.assistant.respond("email the emergency numbers for Kenya to +254700"),
        )
        self.assertIn(
            "is an email address",
            self.assistant.respond("text the emergency numbers for Kenya to me@example.com"),
        )
        self.assertIn(
            "could not prepare",
            self.assistant.respond("text the emergency numbers for Kenya to mum"),
        )


if __name__ == "__main__":
    unittest.main()
