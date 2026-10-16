"""Static, pre-written user-facing messages in English, Nepali (Devanagari) and Romanized Nepali.

These are used where we must not depend on the LLM: emergencies, handoff notices,
fallbacks and failures.
"""
from __future__ import annotations

from typing import Final

STYLES: Final = ("en", "ne", "ne_roman")

_M: dict[str, dict[str, str]] = {
    "greeting": {
        "en": "Welcome to Himalayan Heritage Hotel! I can help with rooms, prices, bookings, the restaurant and local tips. How can I help you today?",
        "ne": "हिमालयन हेरिटेज होटलमा स्वागत छ! म कोठा, भाडा, बुकिङ, रेस्टुरेन्ट र स्थानीय जानकारीमा सहयोग गर्न सक्छु। आज म तपाईंलाई कसरी सहयोग गरूँ?",
        "ne_roman": "Himalayan Heritage Hotel ma swagat chha! Ma kotha, bhada, booking, restaurant ra sthaniya jankari ma sahayog garna sakchhu. Aja ma tapailai kasari sahayog garu?",
    },
    "thanks": {
        "en": "You're welcome! Let me know if there is anything else I can help with.",
        "ne": "धन्यवाद! अरू केही सहयोग चाहिएमा भन्नुहोला।",
        "ne_roman": "Dhanyabad! Aru kehi sahayog chahiyema bhannuhola.",
    },
    "handoff_hold": {
        "en": "I've passed your request to our hotel manager (ticket {ref}). A team member will reply right here shortly. You can keep typing and I'll forward everything.",
        "ne": "मैले तपाईंको अनुरोध होटल म्यानेजरलाई पठाएको छु (टिकट {ref})। हाम्रो टोलीको सदस्यले यहीँ छिट्टै जवाफ दिनुहुनेछ। तपाईं लेख्न जारी राख्न सक्नुहुन्छ, म सबै पठाइदिन्छु।",
        "ne_roman": "Maile tapaiko anurodh hotel manager lai pathaeko chhu (ticket {ref}). Hamro team ko sadasya le yahi chhitai jawaf dinuhunchha. Tapai lekhna jari rakhna sakchhu, ma sabai pathaidinchhu.",
    },
    "handoff_relay": {
        "en": "Your message has been forwarded to our team (ticket {ref}). Someone will reply here soon.",
        "ne": "तपाईंको सन्देश हाम्रो टोलीलाई पठाइएको छ (टिकट {ref})। कसैले यहीँ चाँडै जवाफ दिनुहुनेछ।",
        "ne_roman": "Tapaiko sandesh hamro team lai pathaiyeko chha (ticket {ref}). Kasaile yahi chadai jawaf dinuhunchha.",
    },
    "handoff_resolved": {
        "en": "Our team has closed this request. I'm back to help if you need anything else.",
        "ne": "हाम्रो टोलीले यो अनुरोध टुंग्याएको छ। अरू केही चाहिएमा म फेरि सहयोग गर्न तयार छु।",
        "ne_roman": "Hamro team le yo anurodh tungyaeko chha. Aru kehi chahiyema ma pheri sahayog garna tayar chhu.",
    },
    "emergency": {
        "en": "This sounds urgent. Please call emergency services now: Police 100, Fire 101, Ambulance 102. I'm alerting our manager immediately and the front desk is staffed 24 hours.",
        "ne": "यो जरुरी देखिन्छ। कृपया तुरुन्त आपतकालीन सेवामा फोन गर्नुहोस्: प्रहरी १००, दमकल १०१, एम्बुलेन्स १०२। म तुरुन्त हाम्रो म्यानेजरलाई जानकारी दिँदैछु र फ्रन्ट डेस्क २४ घण्टा खुला छ।",
        "ne_roman": "Yo jaruri dekhinchha. Kripaya turunta aapatkalin sewa ma phone garnuhos: Prahari 100, Damkal 101, Ambulance 102. Ma turunta hamro manager lai jankari dindai chhu ra front desk 24 ghanta khula chha.",
    },
    "no_answer": {
        "en": "I don't have reliable information on that, and I don't want to guess. I'll ask our team to help you.",
        "ne": "यसबारे मसँग भरपर्दो जानकारी छैन र म अन्दाज गर्न चाहन्नँ। म हाम्रो टोलीलाई तपाईंलाई सहयोग गर्न अनुरोध गर्छु।",
        "ne_roman": "Yasbare masanga bharparda jankari chaina ra ma andaj garna chahanna. Ma hamro team lai tapailai sahayog garna anurodh garchhu.",
    },
    "error_generic": {
        "en": "Sorry, something went wrong on my side. Please try again in a moment, or ask for a human and I'll connect you to our team.",
        "ne": "माफ गर्नुहोस्, मेरो तर्फबाट केही समस्या भयो। कृपया केही बेरमा फेरि प्रयास गर्नुहोस्, वा मानिससँग कुरा गर्न भन्नुहोस्।",
        "ne_roman": "Maaf garnuhos, mero tarfa bata kehi samasya bhayo. Kripaya kehi bera ma pheri prayas garnuhos, wa manche sanga kura garna bhannuhos.",
    },
    "llm_unavailable": {
        "en": "I'm having trouble reaching my language service right now. I've asked our team to follow up with you.",
        "ne": "अहिले मेरो भाषा सेवामा समस्या छ। मैले हाम्रो टोलीलाई तपाईंलाई सम्पर्क गर्न अनुरोध गरेको छु।",
        "ne_roman": "Ahile mero bhasha sewa ma samasya chha. Maile hamro team lai tapailai sampark garna anurodh gareko chhu.",
    },
    "notif_sent": {
        "en": "A confirmation has been sent to your phone/email.",
        "ne": "पुष्टिकरण तपाईंको फोन/इमेलमा पठाइएको छ।",
        "ne_roman": "Pushtikaran tapaiko phone/email ma pathaiyeko chha.",
    },
    "out_of_scope": {
        "en": "I can help with Himalayan Heritage Hotel: rooms, prices, bookings, the restaurant, services and local tips. What would you like to know?",
        "ne": "म हिमालयन हेरिटेज होटलबारे सहयोग गर्न सक्छु: कोठा, भाडा, बुकिङ, रेस्टुरेन्ट, सेवा र स्थानीय जानकारी। तपाईं के जान्न चाहनुहुन्छ?",
        "ne_roman": "Ma Himalayan Heritage Hotel bare sahayog garna sakchhu: kotha, bhada, booking, restaurant, sewa ra sthaniya jankari. Tapai ke janna chahanuhunchha?",
    },
    "loop_limit": {
        "en": "This request needs a human touch. I've asked our team to take over.",
        "ne": "यो अनुरोधलाई मानिसको सहयोग चाहिन्छ। मैले हाम्रो टोलीलाई जिम्मा लिन अनुरोध गरेको छु।",
        "ne_roman": "Yo anurodh lai manche ko sahayog chahinchha. Maile hamro team lai jimma line anurodh gareko chhu.",
    },
}


def reply_style_for(language: str, script: str) -> str:
    """Map (language, script) to a message style key."""
    if language == "en":
        return "en"
    return "ne" if script == "devanagari" else "ne_roman"


def msg(key: str, style: str, **fmt: str) -> str:
    """Fetch a static message in the requested style (falls back to English)."""
    table = _M[key]
    text = table.get(style) or table["en"]
    return text.format(**fmt) if fmt else text
