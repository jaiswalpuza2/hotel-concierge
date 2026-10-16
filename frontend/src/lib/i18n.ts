import type { Language } from "./types";

type Dict = Record<string, string>;

const en: Dict = {
  title: "Concierge",
  subtitle: "Rooms, prices, bookings, restaurant and local tips",
  placeholder: "Type your message…",
  send: "Send",
  online: "Connected",
  connecting: "Connecting…",
  offline: "Reconnecting…",
  mic: "Speak",
  micStop: "Stop recording",
  listening: "Listening…",
  voiceReplies: "Voice replies",
  humanBanner: "A team member has been notified and will reply here.",
  humanLabel: "Hotel team",
  sources: "Sources",
  emptyTitle: "Namaste! How can I help?",
  emptyBody: "Ask in English, नेपाली, or Romanized Nepali.",
  micDenied: "Microphone access was blocked. Allow it in your browser settings.",
  micUnsupported: "Voice input is not supported in this browser.",
  stage_routing: "Understanding your request…",
  stage_retrieving: "Searching hotel documents…",
  stage_thinking: "Thinking…",
  stage_tool: "Checking live hotel data…",
  stage_answering: "Writing the answer…",
  stage_notifying: "Sending your confirmation…",
  stage_handoff: "Contacting the manager…",
  stage_transcribing: "Listening to your voice…",
  stage_speaking: "Preparing audio…",
  s1: "Do you have a deluxe room for 2 people from 5 to 8 Kartik?",
  s2: "What time is check-out?",
  s3: "Is airport pickup available?",
  s4: "I want to book a table for dinner",
};

const ne: Dict = {
  title: "कन्सियर्ज",
  subtitle: "कोठा, भाडा, बुकिङ, रेस्टुरेन्ट र स्थानीय जानकारी",
  placeholder: "आफ्नो सन्देश लेख्नुहोस्…",
  send: "पठाउनुहोस्",
  online: "जडान भयो",
  connecting: "जडान हुँदैछ…",
  offline: "पुनः जडान हुँदैछ…",
  mic: "बोल्नुहोस्",
  micStop: "रेकर्डिङ रोक्नुहोस्",
  listening: "सुन्दैछु…",
  voiceReplies: "आवाजमा जवाफ",
  humanBanner: "हाम्रो टोलीलाई जानकारी गराइएको छ; उहाँले यहीँ जवाफ दिनुहुनेछ।",
  humanLabel: "होटल टोली",
  sources: "स्रोत",
  emptyTitle: "नमस्ते! म कसरी सहयोग गरूँ?",
  emptyBody: "अंग्रेजी, नेपाली वा रोमन नेपालीमा सोध्नुहोस्।",
  micDenied: "माइक्रोफोन अनुमति रोकिएको छ। ब्राउजर सेटिङमा अनुमति दिनुहोस्।",
  micUnsupported: "यो ब्राउजरमा आवाज इनपुट समर्थित छैन।",
  stage_routing: "तपाईंको अनुरोध बुझ्दैछु…",
  stage_retrieving: "होटलका कागजात खोज्दैछु…",
  stage_thinking: "सोच्दैछु…",
  stage_tool: "होटलको प्रत्यक्ष जानकारी हेर्दैछु…",
  stage_answering: "जवाफ लेख्दैछु…",
  stage_notifying: "पुष्टिकरण पठाउँदैछु…",
  stage_handoff: "म्यानेजरलाई सम्पर्क गर्दैछु…",
  stage_transcribing: "तपाईंको आवाज सुन्दैछु…",
  stage_speaking: "अडियो तयार गर्दैछु…",
  s1: "५ देखि ८ कात्तिकसम्म २ जनाको लागि डिलक्स कोठा खाली छ?",
  s2: "चेक-आउट समय कति बजे हो?",
  s3: "एयरपोर्ट पिकअप पाइन्छ?",
  s4: "खानाको लागि टेबल बुक गर्न चाहन्छु",
};

const dictionaries: Record<Language, Dict> = { en, ne };

export function t(lang: Language, key: string): string {
  return dictionaries[lang][key] ?? dictionaries.en[key] ?? key;
}
