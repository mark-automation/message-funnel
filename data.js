/* ============================================================
   MessageFunnel — connector layer + demo data
   ------------------------------------------------------------
   Every platform plugs in through the same shape:

     { id, name, color, icon,
       fetchConversations() -> [{
           id, contact: {name},
           unreadCount,
           messages: [{ from: 'them'|'me', text, minutesAgo }]
         }] }

   The bundled connectors are SIMULATED (deterministic sample
   data, timestamps relative to page load so the demo always
   looks fresh). Swapping in real ones later means replacing
   fetchConversations with an authenticated API call routed
   through a small token backend — see README.md.
   ============================================================ */

const ICONS = {
  messenger:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.14 2 11.25c0 2.91 1.45 5.51 3.72 7.2V22l3.4-1.87c.92.26 1.88.39 2.88.39 5.52 0 10-4.14 10-9.27S17.52 2 12 2zm1.06 12.44-2.55-2.72-4.97 2.72 5.47-5.8 2.61 2.72 4.9-2.72-5.46 5.8z"/></svg>',
  instagram:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7.5 2h9A5.5 5.5 0 0 1 22 7.5v9a5.5 5.5 0 0 1-5.5 5.5h-9A5.5 5.5 0 0 1 2 16.5v-9A5.5 5.5 0 0 1 7.5 2zm0 2A3.5 3.5 0 0 0 4 7.5v9A3.5 3.5 0 0 0 7.5 20h9a3.5 3.5 0 0 0 3.5-3.5v-9A3.5 3.5 0 0 0 16.5 4h-9zM12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm5.3-3.4a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4z"/></svg>',
  tiktok:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16.6 3c.36 2.05 1.73 3.62 4.07 3.98v3.13c-1.53.03-2.94-.42-4.07-1.22v6.29c0 3.42-2.72 6.32-6.17 6.32C7.02 21.5 4.3 18.6 4.3 15.18c0-3.37 2.66-6.1 6.04-6.28v3.28c-1.65.17-2.9 1.43-2.9 3 0 1.68 1.38 3.08 3.06 3.08 1.69 0 3.07-1.4 3.07-3.08V3h3.03z"/></svg>',
  whatsapp:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.65 15L2 22l5.15-1.35A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.15 14.83l-.34-.2-3.03.8.81-2.95-.21-.35A8 8 0 0 1 12 4zm-3.1 4.2c-.2 0-.5.07-.74.34-.24.26-.86.84-.86 2.04 0 1.2.87 2.36 1 2.52.12.17 1.72 2.75 4.26 3.74 2.1.82 2.53.66 2.99.62.45-.04 1.47-.6 1.68-1.19.2-.58.2-1.08.15-1.19-.06-.1-.23-.17-.48-.3s-1.47-.72-1.7-.8c-.22-.09-.39-.13-.55.12-.16.25-.63.8-.77.96-.14.17-.28.19-.52.06a6.7 6.7 0 0 1-1.97-1.21 7.3 7.3 0 0 1-1.36-1.69c-.14-.25-.01-.38.11-.5.11-.12.25-.3.37-.45.13-.15.17-.25.26-.42.08-.17.04-.31-.02-.44-.06-.12-.55-1.33-.76-1.82-.2-.47-.4-.41-.55-.41l-.55-.01z"/></svg>',
  telegram:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M21.9 4.6 2.9 12c-.93.37-.9 1.06-.16 1.29l4.7 1.47 1.83 5.6c.22.6.56.75 1.06.42l2.68-1.98 4.6 3.4c.67.37 1.15.18 1.32-.62l2.4-11.3c.24-.98-.37-1.42-1.43-1.08v-4.6zM8.6 14.5l9.2-5.8c.44-.27.85-.13.52.17l-7.85 7.1-.3 3.3-1.57-4.77z"/></svg>',
  x:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17.75 3h3.07l-6.7 7.66L22 21h-6.17l-4.84-6.32L5.46 21H2.38l7.17-8.2L2 3h6.33l4.37 5.78L17.75 3zm-1.08 16.15h1.7L7.42 4.74H5.6l11.07 14.4z"/></svg>'
};

/* Demo auto-replies, per platform flavor */
const DEMO_REPLIES = {
  messenger: ['Haha okay noted 👍', 'Wait lemme check', 'Sounds good!', 'Send it over na lang'],
  instagram: ['omg yes 🔥', 'posting it later hehe', 'let’s collab soon!', 'saw that 👀'],
  tiktok: ['check your cart na 🛒', 'restock Friday!!', 'OMR sent 📦', 'use code BUDOL15'],
  whatsapp: ['Ok anak 🙏', 'Sige, see you!', 'Received po ✔️', 'Ingat!'],
  telegram: ['build passed ✅', 'deploying now', 'logs look clean', '+1'],
  x: ['lol 😂', 'fr fr', 'beta invite sent 🚀', 'mutuals?']
};

/* minute offsets keep the demo perpetually "fresh" */
function mins(m) { return m; }

const CONNECTORS = [
  {
    id: 'messenger', name: 'Messenger', color: '#0084FF',
    icon: ICONS.messenger,
    fetchConversations: () => [
      {
        id: 'ms-1', contact: { name: 'Mara Villanueva' }, unreadCount: 3,
        messages: [
          { from: 'them', text: 'Hi! Following up re: the venue quote 📋', minutesAgo: mins(190) },
          { from: 'them', text: 'Prices lock this Friday so let me know the final headcount by then?', minutesAgo: mins(186) },
          { from: 'me',   text: 'Got it — waiting on two more confirmations', minutesAgo: mins(120) },
          { from: 'them', text: 'Okay! I can hold the rate until Friday 5pm 🙂', minutesAgo: mins(118) },
          { from: 'them', text: 'Also they added a free projector if we book before then', minutesAgo: mins(24) }
        ]
      },
      {
        id: 'ms-2', contact: { name: 'Kuya Ron (catering)' }, unreadCount: 0,
        messages: [
          { from: 'me',   text: 'Chef, locking 42 pax for the 30th', minutesAgo: mins(1500) },
          { from: 'them', text: 'Noted. Buffet setup + lechon de leche as agreed.', minutesAgo: mins(1440) },
          { from: 'them', text: '50% downpayment reserves the date 🙏', minutesAgo: mins(1438) }
        ]
      },
      {
        id: 'ms-3', contact: { name: 'Block 4 GC Rep' }, unreadCount: 1,
        messages: [
          { from: 'them', text: 'Reminder: association dues due end of month', minutesAgo: mins(300) },
          { from: 'me',   text: 'Will transfer tomorrow, thanks!', minutesAgo: mins(280) },
          { from: 'them', text: 'New garbage schedule also posted at the gate', minutesAgo: mins(95) }
        ]
      }
    ]
  },
  {
    id: 'instagram', name: 'Instagram', color: '#E1306C',
    icon: ICONS.instagram,
    fetchConversations: () => [
      {
        id: 'ig-1', contact: { name: '@atelier.nico' }, unreadCount: 2,
        messages: [
          { from: 'them', text: 'your feed is exactly the aesthetic we want for our launch 👀', minutesAgo: mins(420) },
          { from: 'them', text: 'open to a paid collab for our march drop? reel + 3 stories', minutesAgo: mins(418) },
          { from: 'me',   text: 'Hey! Yes interested — send the brief and rates?', minutesAgo: mins(400) },
          { from: 'them', text: 'sending the deck now 💸', minutesAgo: mins(55) },
          { from: 'them', text: 'budget range is flexible for the right fit', minutesAgo: mins(53) }
        ]
      },
      {
        id: 'ig-2', contact: { name: '@danlifts' }, unreadCount: 0,
        messages: [
          { from: 'them', text: 'that 140kg PR was insane 🔥🔥', minutesAgo: mins(2600) },
          { from: 'me',   text: 'haha thanks bro, next stop 150', minutesAgo: mins(2500) },
          { from: 'them', text: 'gym saturday?', minutesAgo: mins(2490) }
        ]
      },
      {
        id: 'ig-3', contact: { name: '@cafe.hiraya' }, unreadCount: 0,
        messages: [
          { from: 'me',   text: 'is the latte art workshop still open for sept?', minutesAgo: mins(4300) },
          { from: 'them', text: 'Yes! Sept 14 slot still available ☕', minutesAgo: mins(4250) }
        ]
      }
    ]
  },
  {
    id: 'tiktok', name: 'TikTok', color: '#FE2C55',
    icon: ICONS.tiktok,
    fetchConversations: () => [
      {
        id: 'tt-1', contact: { name: '@budol.finds' }, unreadCount: 1,
        messages: [
          { from: 'me',   text: 'hi! order #2214 shipped na ba?', minutesAgo: mins(500) },
          { from: 'them', text: 'shipped yesterday! J&T tracking sent to your email 📦', minutesAgo: mins(480) },
          { from: 'them', text: 'eta wednesday po', minutesAgo: mins(60) }
        ]
      },
      {
        id: 'tt-2', contact: { name: '@kai.edits' }, unreadCount: 0,
        messages: [
          { from: 'them', text: 'yo the preset pack mo, may mobile version?', minutesAgo: mins(2000) },
          { from: 'me',   text: 'yep, included sa zip — lightroom mobile dng files', minutesAgo: mins(1950) },
          { from: 'them', text: 'copped ✅', minutesAgo: mins(1900) }
        ]
      }
    ]
  },
  {
    id: 'whatsapp', name: 'WhatsApp', color: '#25D366',
    icon: ICONS.whatsapp,
    fetchConversations: () => [
      {
        id: 'wa-1', contact: { name: 'Mama' }, unreadCount: 2,
        messages: [
          { from: 'them', text: 'Anak, dinner here Sunday ha 🙏', minutesAgo: mins(700) },
          { from: 'me',   text: 'Yes po, I’ll bring dessert 🍰', minutesAgo: mins(650) },
          { from: 'them', text: 'Your tita is asking kung kelan ka ulit may pasok', minutesAgo: mins(80) },
          { from: 'them', text: 'Ingat always ❤️', minutesAgo: mins(78) }
        ]
      },
      {
        id: 'wa-2', contact: { name: 'Arben (landlord)' }, unreadCount: 0,
        messages: [
          { from: 'me',   text: 'Sent the rent via bank transfer, ref 88213', minutesAgo: mins(2900) },
          { from: 'them', text: 'Received, sending the official receipt photo.', minutesAgo: mins(2800) },
          { from: 'them', text: 'Water bill na rin enclosed po', minutesAgo: mins(2790) }
        ]
      }
    ]
  },
  {
    id: 'telegram', name: 'Telegram', color: '#229ED9',
    icon: ICONS.telegram,
    fetchConversations: () => [
      {
        id: 'tg-1', contact: { name: 'Den (ops)' }, unreadCount: 1,
        messages: [
          { from: 'them', text: 'nightly build passed, all green ✅', minutesAgo: mins(140) },
          { from: 'me',   text: 'nice — ship it to staging', minutesAgo: mins(130) },
          { from: 'them', text: 'staging deployed, smoke tests running now', minutesAgo: mins(40) }
        ]
      },
      {
        id: 'tg-2', contact: { name: 'Board Exam Study Group' }, unreadCount: 0,
        messages: [
          { from: 'them', text: 'poll: mock exam sat or sun?', minutesAgo: mins(1800) },
          { from: 'me',   text: 'sat works', minutesAgo: mins(1700) },
          { from: 'them', text: 'sun wins 6-3 😅 see everyone sunday 9am', minutesAgo: mins(1600) }
        ]
      }
    ]
  },
  {
    id: 'x', name: 'X', color: '#111111',
    icon: ICONS.x,
    fetchConversations: () => [
      {
        id: 'x-1', contact: { name: '@shipgurl' }, unreadCount: 0,
        messages: [
          { from: 'me',   text: 'hey! any beta invites left for the launch?', minutesAgo: mins(900) },
          { from: 'them', text: 'yes! dm’d you the code 🚀', minutesAgo: mins(850) },
          { from: 'me',   text: 'got in, thanks!! feedback coming this week', minutesAgo: mins(800) }
        ]
      },
      {
        id: 'x-2', contact: { name: '@devnull_za' }, unreadCount: 0,
        messages: [
          { from: 'them', text: 'sent you the meme template lol', minutesAgo: mins(3200) },
          { from: 'me',   text: '💀💀💀 using this everywhere', minutesAgo: mins(3100) }
        ]
      }
    ]
  }
];

/* Export for app.js (plain script tags, no modules needed on Pages) */
if (typeof window !== 'undefined') {
  window.MF_CONNECTORS = CONNECTORS;
  window.MF_DEMO_REPLIES = DEMO_REPLIES;
}
