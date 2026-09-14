# ============================================================
#  MM Promo Bot - guided deploy  (Windows PowerShell 5.1 / 7.x)
#
#      powershell -ExecutionPolicy Bypass -File .\deploy.ps1
#
#  Dobara chalana safe hai. Jo step ho chuka hai wo skip ho jayega.
#  Secrets seedha `gh` ko jaate hain - ye script unhe na file me
#  likhti hai, na screen pe dikhati hai.
# ============================================================

$ErrorActionPreference = "Stop"
$REPO = "mm-promo-bot"

# --- native commands ------------------------------------------------
# Windows PowerShell 5.1 me native command ka stderr ErrorActionPreference
# =Stop ke saath terminating error ban jata hai - aur gh/git normal kaam
# me bhi stderr pe likhte hain (git push ka progress, gh ka "not found").
# Isliye har native call yahin se jata hai, exit code se judge hota hai.
function Invoke-Native {
    param([scriptblock]$Block, [switch]$Quiet)
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) { & $Block 2>&1 | Out-Null }
        else        { & $Block 2>&1 | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkGray } }
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
}
function Probe([scriptblock]$Block) { Invoke-Native $Block -Quiet }
function Must($label, [scriptblock]$Block) {
    $rc = Invoke-Native $Block
    if ($rc -ne 0) { throw "$label fail ho gaya (exit code $rc). Upar ka message dekho, fix karke script dobara chala do." }
}
function Capture([scriptblock]$Block) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { return (& $Block 2>$null) } finally { $ErrorActionPreference = $old }
}

function Step($n, $t) { Write-Host "`n===[ $n ] $t" -ForegroundColor Cyan }
function Ok($t)       { Write-Host "    OK   $t" -ForegroundColor Green }
function Warn($t)     { Write-Host "    --   $t" -ForegroundColor Yellow }
function Info($t)     { Write-Host "         $t" -ForegroundColor Gray }
function Ask($t)      { Read-Host "    $t" }
function Hold($t)     { Read-Host "    $t (ho jaye to Enter dabao)" | Out-Null }

function SetSecret($name, $value, $owner) {
    if ([string]::IsNullOrWhiteSpace($value)) { Warn "$name skip kiya"; return }
    $v = $value.Trim()
    $rc = Probe { $v | gh secret set $name --repo "$owner/$REPO" }
    if ($rc -eq 0) { Ok "$name saved" } else { Warn "$name save nahi hua (exit $rc)" }
}

# ---------------------------------------------------------------- checks
if (-not (Test-Path ".\config.yaml") -or -not (Test-Path ".\bot\propose.py")) {
    throw "Ye script mm-promo-bot folder ke ANDAR se chalao."
}
foreach ($c in @(@("git","https://git-scm.com"), @("gh","https://cli.github.com"),
                 @("python","https://python.org"))) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) {
        throw "$($c[0]) install nahi hai. Yahan se lo: $($c[1])"
    }
}

Write-Host "`n  MM PROMO BOT - DEPLOY  (script v6)" -ForegroundColor White
Write-Host "  Har 3 din: Instagram Story + Facebook + LinkedIn.`n" -ForegroundColor White

# ---------------------------------------------------------------- 1
Step 1 "GitHub login"
if ((Probe { gh auth status }) -ne 0) {
    Info "Browser khulega - GitHub me login karo."
    Must "gh auth login" { gh auth login }
}
$OWNER = (Capture { gh api user --jq .login })
if ([string]::IsNullOrWhiteSpace($OWNER)) { throw "GitHub username nahi mila. 'gh auth login' chala ke dobara try karo." }
$OWNER = $OWNER.Trim()
Ok "signed in as $OWNER"

# ---------------------------------------------------------------- 2
Step 2 "Repository"
if ((Probe { gh repo view "$OWNER/$REPO" }) -eq 0) {
    Warn "$OWNER/$REPO pehle se hai - wahi use kar rahe hain"
} else {
    Info "Nayi public repo ban rahi hai."
    Info "Public isliye ki Instagram image ka upload accept nahi karta -"
    Info "wo ek public URL khud fetch karta hai. Tokens code me kabhi nahi"
    Info "jaate, wo GitHub Secrets me rehte hain."
    Must "repo create" {
        gh repo create "$OWNER/$REPO" --public `
            --description "Auto-posts a Mythical Motions promo to Instagram + LinkedIn every 3 days."
    }
    Ok "created $OWNER/$REPO"
}

# ---------------------------------------------------------------- 3
Step 3 "Code push"
if (-not (Test-Path ".\.git")) { Must "git init" { git init -b main } }
Probe { git remote remove origin } | Out-Null
Must "git remote add" { git remote add origin "https://github.com/$OWNER/$REPO.git" }
Must "git add"        { git add -A }
Probe { git commit -m "MM Promo Bot" --allow-empty } | Out-Null
Must "git branch"     { git branch -M main }
Must "git push"       { git push -u origin main --force }
Ok "pushed to main"

$rc = Probe {
    gh api -X PUT "repos/$OWNER/$REPO/actions/permissions/workflow" `
        -f default_workflow_permissions=write `
        -F can_approve_pull_request_reviews=false
}
if ($rc -eq 0) { Ok "workflows ko write permission mil gayi" }
else { Warn "workflow permission set nahi hui - Settings > Actions > General me 'Read and write' select kar dena" }

# ---------------------------------------------------------------- 4
Step 4 "GitHub Pages (yahan se Instagram images uthata hai)"
$rc = Probe { gh api -X POST "repos/$OWNER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" }
if ($rc -ne 0) {
    $rc = Probe { gh api -X PUT "repos/$OWNER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" }
}
$PAGES = "https://$OWNER.github.io/$REPO"
if ($rc -eq 0) { Ok "Pages -> $PAGES" }
else { Warn "Pages khud on nahi hui - Settings > Pages > Deploy from a branch: main / docs" }
Info "pehli build me 1-2 minute lagte hain"
SetSecret "PUBLIC_BASE_URL" $PAGES $OWNER

# ---------------------------------------------------------------- 5
Step 5 "Discord (preview + community post)"
Info "Webhook chahiye - ye sirf 20 second ka kaam hai, koi bot nahi:"
Info "  Discord me ek private channel banao (jaise #promo-approvals)"
Info "  Channel pe right-click -> Edit Channel -> Integrations"
Info "  -> Webhooks -> New Webhook -> Copy Webhook URL"
Info ""
Info "Webhook sirf bhej sakta hai, padh nahi sakta - ye Discord ki"
Info "limitation hai. Isliye post window ke baad apne aap chala jayega."
Info "Rokna ho to: GitHub > Actions > 'Cancel pending post' > Run workflow."
Start-Process "https://discord.com/app"
Hold "Webhook URL mil gaya?"
SetSecret "DISCORD_WEBHOOK_URL" (Ask "Webhook URL paste karo") $OWNER

Info ""
Info "Ab ek DOOSRA channel - jahan promo khud post hoga (community ke liye)."
Info "Ye approval wale channel se alag hona chahiye, warna members ko"
Info "'ye post karein?' wala preview dikh jayega."
Info "Usi tarah: channel > Edit Channel > Integrations > Webhooks > New."
Hold "Doosre channel ka webhook mil gaya?"
SetSecret "DISCORD_POST_WEBHOOK_URL" (Ask "Community channel ka webhook URL") $OWNER

Info ""
Info "(Optional) Agar baad me Discord pe seedha checkmark/cross se approve"
Info "karna ho, to ek bot bana ke DISCORD_BOT_TOKEN aur DISCORD_CHANNEL_ID"
Info "secrets daal dena - code khud approval mode pe switch ho jayega."

# ---------------------------------------------------------------- 6
Step 6 "Instagram Story + Facebook Page (Meta)"
Info "Dono ek hi token se chalte hain. Long-lived USER token ya Page token -"
Info "dono chalenge, code Page token khud nikal lega."
Info ""
Info "NOTE: Windows console lambi line ko ~254 characters pe kaat deta hai,"
Info "aur Meta token usse lamba hota hai. Isliye token FILE se padha jata hai,"
Info "paste se nahi - warna wo chup-chaap adhoora save ho jata."

$igid = Ask "Instagram user id (Enter = 17841402294595690)"
if ([string]::IsNullOrWhiteSpace($igid) -or $igid -notmatch '^\d{6,}$') {
    if (-not [string]::IsNullOrWhiteSpace($igid)) { Warn "'$igid' valid id nahi hai - default le rahe hain" }
    $igid = "17841402294595690"
}
$fbid = Ask "Facebook Page id (Enter = 1276111598923180)"
if ([string]::IsNullOrWhiteSpace($fbid) -or $fbid -notmatch '^\d{6,}$') {
    if (-not [string]::IsNullOrWhiteSpace($fbid)) { Warn "'$fbid' valid id nahi hai - default le rahe hain" }
    $fbid = "1276111598923180"
}
SetSecret "IG_USER_ID" $igid $OWNER
SetSecret "FB_PAGE_ID" $fbid $OWNER

# Reuse the token that mm-story-bot already uses, if it is on this PC.
$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$tokenPaths = @(
    (Join-Path (Get-Location) "token.txt"),
    (Join-Path $UserHome "MythicalMotions\mm-story-bot\token.txt"),
    (Join-Path $UserHome "mm-story-bot\token.txt")
)
$metaToken = ""
foreach ($tp in $tokenPaths) {
    if (Test-Path $tp) {
        $metaToken = ((Get-Content $tp -Raw) -replace "\s", "")
        if ($metaToken.Length -ge 100) { Ok "Token mil gaya: $tp ($($metaToken.Length) chars)"; break }
        Warn "$tp me token chhota hai ($($metaToken.Length) chars) - chhod rahe hain"
        $metaToken = ""
    }
}
if (-not $metaToken) {
    Info ""
    Info "token.txt kahin nahi mili. Do me se ek karo:"
    Info "  a) Is folder me 'token.txt' banao, token paste karke save karo"
    Info "  b) mm-story-bot wali copy karo:"
    Info "     copy `"$UserHome\MythicalMotions\mm-story-bot\token.txt`" ."
    Hold "token.txt ban gayi?"
    foreach ($tp in $tokenPaths) {
        if (Test-Path $tp) {
            $metaToken = ((Get-Content $tp -Raw) -replace "\s", "")
            if ($metaToken.Length -ge 100) { Ok "Token mil gaya ($($metaToken.Length) chars)"; break }
            $metaToken = ""
        }
    }
}
if ($metaToken) {
    SetSecret "META_PAGE_TOKEN" $metaToken $OWNER
} else {
    Warn "Meta token skip - Instagram aur Facebook abhi post nahi kar payenge."
    Info "Baad me: gh secret set META_PAGE_TOKEN --repo $OWNER/$REPO < token.txt"
}

# ---------------------------------------------------------------- 7
Step 7 "LinkedIn"
Info "MM Publisher wali LinkedIn app hi chalegi - nayi banane ki zarurat"
Info "nahi. Us app ke Auth tab me pehle ye redirect URL add karo:"
Info ""
Info "    http://localhost:8731/callback"
Info ""
Start-Process "https://www.linkedin.com/developers/apps"
Hold "Redirect URL add ho gaya?"
$liId  = Ask "LinkedIn Client ID"
$liSec = Ask "LinkedIn Client Secret"
if ($liId -and $liSec) {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) "mm-li-$(Get-Random).json"
    try {
        Probe { python -m pip install requests --quiet } | Out-Null
        $auth = Join-Path "tools" "linkedin_auth.py"
        $rc = Invoke-Native { python $auth --client-id $liId --client-secret $liSec --json $tmp }
        if ($rc -eq 0 -and (Test-Path $tmp)) {
            $li = Get-Content $tmp -Raw | ConvertFrom-Json
            SetSecret "LINKEDIN_ACCESS_TOKEN" $li.access_token $OWNER
            SetSecret "LINKEDIN_PERSON_URN"   $li.person_urn   $OWNER
            SetSecret "LINKEDIN_TOKEN_ISSUED" $li.issued       $OWNER
            Ok "LinkedIn connected - token copy karne ki zarurat hi nahi padi"
        } else {
            Warn "LinkedIn login poora nahi hua - baad me ye chala lena:"
            Info "python tools/linkedin_auth.py --client-id X --client-secret Y"
        }
    } finally {
        if (Test-Path $tmp) { Remove-Item $tmp -Force }
    }
} else {
    Warn "LinkedIn skip kiya"
}

# ---------------------------------------------------------------- 8
Step 8 "Pehla test (dry run - Instagram/LinkedIn pe kuch nahi jayega)"
$go = Ask "Abhi ek test post banaye aur Discord pe bheje? (y/n)"
if ($go -match '^[yY]') {
    $rc = Probe { gh workflow run "Propose post" --repo "$OWNER/$REPO" -f force=true -f dry_run=true }
    if ($rc -eq 0) { Ok "chal gaya - 2-3 minute me Discord pe preview aayega" }
    else { Warn "workflow trigger nahi hua - Actions tab se manually 'Run workflow' kar do" }
}

Write-Host @"

  ====================================================================
  DEPLOY DONE

  Repo      https://github.com/$OWNER/$REPO
  Pages     $PAGES
  Actions   https://github.com/$OWNER/$REPO/actions

  Cancel karna ho: Actions > Cancel pending post > Run workflow

  Discord pe preview sahi lage to asli post ke liye:
      Actions > Propose post > Run workflow
      force = true, dry_run = FALSE

  Uske baad kuch nahi karna - har 3 din apne aap chalega.
  ====================================================================

"@ -ForegroundColor Green
