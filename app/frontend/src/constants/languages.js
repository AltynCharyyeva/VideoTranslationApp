// Shared list of languages supported as translation targets, with the
// matching codes for NLLB (translation) and Whisper (source detection).
export const LANGUAGES = [
  { name: "Turkmen", nllb: "tuk_Latn", whisper: "tk" },
  { name: "Romanian", nllb: "ron_Latn", whisper: "ro" },
  { name: "German", nllb: "deu_Latn", whisper: "de" },
  { name: "Turkish", nllb: "tur_Latn", whisper: "tr" },
  { name: "Russian", nllb: "rus_Cyrl", whisper: "ru" },
  { name: "English", nllb: "eng_Latn", whisper: "en" },
  { name: "Kazakh", nllb: "kaz_Cyrl", whisper: "kk" },
  { name: "Uzbek", nllb: "uzb_Latn", whisper: "uz" },
  { name: "Kyrgyz", nllb: "kir_Cyrl", whisper: "ky" },
];

export const getLanguageNameByNLLB = (code) =>
  LANGUAGES.find((lang) => lang.nllb === code)?.name || code;

export const getLanguageNameByWhisper = (code) =>
  LANGUAGES.find((lang) => lang.whisper === code)?.name || code;
