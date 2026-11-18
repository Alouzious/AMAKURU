const catalogues = {
  en: {
    open: "Ask Amakuru",
    close: "Close",
    welcome: "How can we help?",
    placeholder: "Type your question\u2026",
    send: "Send",
    privacy: "Please do not type personal details.",
    offline: "You appear offline. Try again when connected.",
    slow: "Still working\u2026 slow network.",
    talking: "Talk to a person",
    thumbsUp: "Helpful",
    thumbsDown: "Not helpful",
    source: "Source"
  },
  lg: {
    open: "Buuza Amakuru",
    close: "Ggalawo",
    welcome: "Tukuyambe otya?",
    placeholder: "Wandiika ekibuuzo\u2026",
    send: "Sindika",
    privacy: "Totuula bipande bya buntu.",
    offline: "Toli ku mukutu. Gezaako ate.",
    slow: "Tukyagala\u2026 mukutu gwa mangu.",
    talking: "Yogera ne muntu",
    thumbsUp: "Kirungi",
    thumbsDown: "Sikirungi",
    source: "Ensibuko"
  },
  nyn: {
    open: "Buzza Amakuru",
    close: "Funga",
    welcome: "Tukuhereze ota?",
    placeholder: "Handiika ekibuuzo\u2026",
    send: "Sindika",
    privacy: "Otandiika ebya buntu.",
    offline: "Tori ku mukutu.",
    slow: "Turacyari\u2026",
    talking: "Gamba na muntu",
    thumbsUp: "Kirungi",
    thumbsDown: "Tikiri gye",
    source: "Ensibuko"
  },
  sw: {
    open: "Uliza Amakuru",
    close: "Funga",
    welcome: "Tunaweza kusaidia vipi?",
    placeholder: "Andika swali lako\u2026",
    send: "Tuma",
    privacy: "Usitoe taarifa binafsi.",
    offline: "Hauna mtandao.",
    slow: "Bado inafanya kazi\u2026",
    talking: "Zungumza na mtu",
    thumbsUp: "Inasaidia",
    thumbsDown: "Haisaidii",
    source: "Chanzo"
  }
};
function t(lang, key) {
  return catalogues[lang]?.[key] ?? catalogues.en[key] ?? key;
}
export {
  t
};
