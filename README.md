# MM Promo Bot

Har 3 din Mythical Motions ka ek promo — image khud banata hai, description
khud likhta hai, aur **Instagram Story + Facebook Page + LinkedIn + Discord**
pe khud post kar deta hai.

Chalti hai GitHub Actions pe. Aapka PC band ho tab bhi chalega. Cost ₹0.

```
  Day 0, 1:30 PM IST          Discord                Live (4h baad)
  ────────────────────        ───────                ──────────────
  2 images render:            preview aata hai       Instagram Story  (9:16)
   • 9:16  story               + caption             Facebook Page    (+ caption)
   • 1:1   feed                                      LinkedIn         (+ caption)
                                                     Discord community(+ caption)
```

**Instagram Story me caption nahi jaati.** Meta story ke liye caption ya link
sticker ka koi API deta hi nahi. Isliye story wali image me saara text —
headline, CTA, aur URL — image ke andar hi render hota hai. Facebook aur
LinkedIn pe pura description normal caption ki tarah jaata hai.

---

## Deploy

`git`, `python` aur [GitHub CLI](https://cli.github.com) install hone
chahiye. Phir is folder ke andar bas ye:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy.ps1
```

Script ye sab khud karti hai — repo banana, code push, Actions
permissions, GitHub Pages on, saare secrets set karna, aur pehla test
chalana. Beech me sirf teen jagah aapko type karna hai, kyunki wahan
aapka login chahiye aur wo koi script nahi kar sakti:

| Kahan | Kya chahiye |
|---|---|
| **Discord** | **do** webhook URL — ek approval/preview channel ka, ek community channel ka jahan promo khud post hoga. Dono alag channel hone chahiye, warna members ko preview dikhega. (channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy) |
| **Meta** | wahi token jo **mm-story-bot** use karta hai — `token.txt` file me. Windows console lambi line ~254 chars pe kaat deta hai, isliye token file se padha jata hai, paste se nahi |
| **LinkedIn** | MM Publisher wali app ka client id + secret. Script login khud chala kar token seedha GitHub Secrets me daal degi — aapko token copy tak nahi karna padega. Bas us app ke Auth tab me `http://localhost:8731/callback` pehle add kar do |

Repo **public** banti hai — Instagram image ka upload accept nahi karta,
wo public URL khud fetch karta hai. Tokens code me kabhi nahi jaate, wo
GitHub Secrets me rehte hain.

Baad me koi secret badalna ho:

```
gh secret set NAME --repo <user>/mm-promo-bot
```

---

## Pehla post

Deploy ke baad Discord pe ek **dry run** preview aayega — image + caption,
par Instagram/LinkedIn pe kuch nahi jayega. Sahi lage to:

**Actions → Propose post → Run workflow** → `force = true`,
`dry_run = false`

Bas. Uske baad har 3 din apne aap.

---

## Roz ka use

Kuch karne ki zarurat nahi. Har 3 din Discord pe preview aayega, aur
4 ghante baad post chala jayega.

Koi post nahi chahiye to: **Actions → Cancel pending post → Run workflow**.

### Chahiye to ✅/❌ wala approval bhi mil sakta hai

Webhook sirf bhej sakta hai, padh nahi sakta — ye Discord ki limitation hai,
isliye reactions webhook mode me kaam nahi karte. Agar baad me seedha Discord
se approve/skip karna ho, to ek bot bana ke ye do secrets daal do:

```
gh secret set DISCORD_BOT_TOKEN  --repo <user>/mm-promo-bot
gh secret set DISCORD_CHANNEL_ID --repo <user>/mm-promo-bot
```

Code khud approval mode pe switch ho jayega — kuch badalna nahi padega.

---

## Content badalna

Saara text `content/posts.yaml` me hai. Edit karke commit — bas.
Naya post add karne ke liye existing block copy karke fields badal do.

Image dekhne ke liye (bina post kiye):

```bash
python tools/preview.py            # poora deck
python tools/preview.py belt-04    # ek post
# out/preview/ me PNG mil jayenge
```

## Settings badalna

Sab `config.yaml` me:

| Setting | Kya karta hai |
|---|---|
| `schedule.interval_days` | kitne din me ek post (default 3) |
| `schedule.auto_approve_hours` | react na karo to kitni der baad auto-post (4) |
| `schedule.ist_publish_window` | auto-post sirf is IST window me (9–22) |
| `tracks.rotation` | kaunse track kis order me. Naam repeat karoge to wo zyada aayega |
| `platforms.instagram_story / facebook / linkedin / discord` | kisi ko band karna ho to `false` |
| `brand.*` | colours, fonts, handle |
| `links.*` | saare URLs ek jagah |

Logo lagana ho to `assets/logo.png` rakh do (square PNG) — "MM" ki jagah
wahi aa jayega.

---

## Design decisions (kyun aisa banaya)

* **3-din ka gap cron se nahi, state se aata hai.** GitHub cron reliable
  nahi hai — run late ho sakti hai ya skip. Isliye workflow roz chalti hai
  aur code `state/history.json` dekh ke decide karta hai. Missed run se
  schedule shift nahi hota, aur double post kabhi nahi hota.
* **Approval do alag runs me hai.** GitHub Actions 4 ghante baithkar
  reaction ka intezaar nahi kar sakti. Isliye propose (roz) aur publish
  (har ghante) alag hain, beech ki state repo me commit hoti hai.
* **Meta token file se aata hai, paste se nahi.** Windows console lambi
  line ko ~254 characters pe kaat deta hai aur Meta token usse lamba hai —
  paste karne pe wo chup-chaap adhoora save ho jata tha.
* **Token user ka ho ya Page ka, dono chalte hain.** Facebook feed post ke
  liye Page token chahiye; agar user token diya gaya to code khud
  `/{page-id}?fields=access_token` se Page token nikal leta hai.
* **Fonts repo me bundled hain**, Google Fonts se fetch nahi hote. Network
  slow ho to font chupchap badal jata — post ka look hi badal jata. Ab
  render fail ho jayega instead of galat font ke saath post hone ke.
* **Partial failure safe hai.** Agar Instagram ho gaya aur LinkedIn fail,
  to agli hourly run sirf LinkedIn retry karegi — Instagram dobara post
  nahi hoga. 3 attempt ke baad Discord pe bata ke ruk jayega.
* **LinkedIn ke do API paths** hain (naya versioned + purana ugcPosts).
  App ki age ke hisaab se kaunsa chalega ye pehle se pata nahi — isliye
  naya try hota hai aur 403/426 pe apne aap purane pe chala jata hai.

## Kuch galat ho to

| Discord pe dikha | Matlab |
|---|---|
| `Image URL not publicly reachable` | Pages off hai ya repo private hai |
| `pages_manage_posts nahi hai` | Meta token me wo permission add karke naya token banao |
| `LinkedIn ... 401` | token expire — `tools/linkedin_auth.py` dobara chalao |
| `Container ... ERROR` | Meta token/Page link ka issue — `tools/check_setup.py` chalao |
| kuch bhi nahi aaya | Actions tab kholo, propose run ka log dekho |

LinkedIn token ~60 din chalta hai. Bot khud Discord pe 12 din pehle warn
kar dega.
