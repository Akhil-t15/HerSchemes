TO BUILD ANY MODULE/FEATURE, YOU MUST SEARCH WEB FOR BEST PRACTICES TO SAVE TIME. 
RESEARCH MORE ON LIVE VOICE AGENT BECAUSE THIS IS OUR SELLING POINT- FOCUS ON LOW LATENCY, FEATURES LIKE BARGE IN, FAST REPLIES, NATURAL INTERUPTIONS, CLEAN AUDIO, SAFETY NET & TRACKING [ IF VOICE IS DOWN-INDICATE USERS TO USE TEXT MODE] ETC

NOTE-NEVER HARDCODE – THE APP SHOULD WORK LIKE A LIVE APPLICATION



Prompt 1: The Big Idea & Ground Rules
"Hey, I have an idea I want to build with you. In Telangana, a lot of women running small businesses—like rural SHG members, tailors, artisans, and shop owners—miss out on government schemes because the rules are confusing,overlapping with central schemes and in hard English. I want to build a completely free web app “HerScheme” (and later WhatsApp -from which users can directly interact with out mcp server [tools]) without the need of opening the app , that helps them find the right schemes in simple Telugu and English.
Before we start building, I have a few strict promises we must never break:
•	Never promise or 'guarantee' a scheme—always say 'Likely Eligible' or 'Needs More Info'.
•	Never ask for or save sensitive IDs like Aadhaar, PAN, Voter ID, Ration Card, or bank account numbers.
•	The AI should never guess or make up scheme rules from its own head. Every rule, fee, and link should live in our database so an admin can edit them easily, and every scheme must point to an official government website.
Based on this idea, how should we set up the foundation and database for our 6 starting schemes (Indira Mahila Shakti, Stree Nidhi, PM Vishwakarma, PMEGP, PM Mudra, and Telangana MSME Policy)? Figure out the cleanest way to gather, ingest them and structure this so it's easy to test locally and ready for production." 

link module 7 – Admins can upload a scheme that can be saved into DB or update it
Prompt 2: The Simple Home Screen (Module 1)
"Now let's think about the first screen a woman sees when she opens the app. I don't want any login wall or long boring forms. She should be able to switch between Telugu and English, and just talk or type in plain language about her business.
To make it super easy for someone who doesn't like typing, I want a big Mic button, a simple text box, and 5 quick- queries ,that fill in her details automatically. I also want 4 clickable demo profiles—like a rural pickle maker or a Warangal tailor—so anyone testing the app can see how it works in one click. And if the mic [voice agent]  doesn't work or credits run out, the text chat should still work smoothly without crashing.
How would you design and build this home screen so it feels super friendly on a mobile phone?" 
Prompt 3: The Privacy Shield (Module 2)
"Here is a big worry I have: even if we tell women not to share their Aadhaar, PAN, ration card, or bank account numbers, someone might still type or say it by mistake.
I want a safety shield that sits in front of our AI and database. First, show a clear warning in Telugu and English telling them not to share private IDs. Second, if a private ID number ever slips into a message or voice transcript, catch it immediately in memory, hide it before the AI or database ever sees it, and gently warn the user on screen. Also, we should never save raw voice recordings.
Figure out the best way to build this privacy layer so nothing sensitive ever leaks into our logs or database." 
Prompt 4: Smart Follow-Up Chat (Module 3)
"Most women won't know what details matter for a government loan. If she just says 'I want to start a tailoring shop,' our assistant shouldn't give up or dump a 10-question survey on her.
I want the assistant to figure out what key facts are missing—like whether she's in a village or town, part of an SHG, starting new or already running, how much loan she needs, or if she had a past government loan—and ask just 1 or 2 short, friendly questions in Telugu or English, explaining why it matters. After 2 tries, or if she skips, it should stop asking and just show the best matches it can, marking unsure ones as 'Needs More Info'. Also, let's make sure the AI has a backup model if the main one is slow or down, and some guardrails so it doesn't loop forever or burn through our daily budget.
How should we design this conversation flow?" 
Prompt 5: The Scheme Matching Brain (Module 4)
"Now let's build the brain that actually checks which schemes she qualifies for. I want this matching logic to be a shared, read-only engine that reads strictly from our database—no AI guessing.
When it finds matches, I want them organized into 3 simple lanes so she isn't overwhelmed:
1.	Telangana State schemes first (like Indira Mahila Shakti and Stree Nidhi).
2.	Central loan options (PM Vishwakarma, PMEGP, and the right Mudra loan band based on her amount).
3.	Free add-on boosters (like Free Udyam and Telangana MSME Policy).
Also, some schemes clash—for example, you can't take both PM Vishwakarma and PMEGP. If two matched schemes conflict, show a clear orange 'Pick One' alert explaining why, straight from our database. And for every scheme, show why she matched, the official government link, and a warning badge if the info hasn't been checked in over 30 days.
Figure out how to build this matching engine so it's 100% accurate and easy to explain to the user." 
Prompt 6: The Anti-Middleman Checklist (Module 5)
"A huge problem on the ground is middlemen charging women money for things that are actually free—like Udyam registration.
When a woman taps on a matched scheme, I want her to see a clear, honest checklist in Telugu and English split into three parts:
•	Free papers (₹0)—with a bold warning that Udyam is 100% free and never to pay an agent.
•	MeeSeva certificates—showing the real government fee and how many days it takes.
•	Where to apply for free—the exact official portal or local office, plus a simple 4-step guide.
Give her a button to easily save or share this checklist on WhatsApp. How should we structure and build this?" 
Prompt 7: Keeping Rules Updated — Admin Console (Module 7)
"Government rules and fees change all the time, and I don't want to rewrite code every time a new Government Order (G.O.) comes out.
I want a private Admin Console behind a login where an admin can upload a G.O. PDF or paste a notice to Ingest new schemes into DB or update. The system should read it, compare it against our live database rules, and show a side-by-side comparison only if something actually changed. Nothing should go live automatically—the admin must click 'Approve & Publish' (which updates the verified date and keeps an audit trail) or 'Dismiss'. Later, we can also add a button to check official websites automatically.
How would you design this admin approval workflow?" 
Prompt 8: Keeping It Free — Partners & Impact (Module 8)
"I want this app to stay ₹0 for women forever. To pay for our servers and APIs, my idea is to work with partner banks and CSR sponsors ethically.
Here is how I imagine it:
•	On bank loan schemes, add an optional, unchecked switch asking if she wants a partner bank to call her for free. Only if she turns it on do we save her contact—and we auto-delete it after 30 days.
•	Give partner banks a private login to see only those opt-in leads.
•	Give sponsors a private Impact Dashboard showing big-picture stats—like how many women were helped, top districts, top schemes, and our average cost per session—with zero personal data.
•	Put a quiet 'Admin / Partner Login' link in the footer, and only allow the admin to create partner or sponsor accounts.
Figure out how to build the logins, role permissions, and dashboards cleanly." 
Prompt 9: WhatsApp & Live Voice (Stretch Features)
"Once our core web app is solid and tested, I want to add two more ways for women to reach us:
1.	WhatsApp: Connect our exact same scheme-matching brain to WhatsApp (using Twilio Sandbox for testing). Women should be able to send Telugu, English, or Tenglish text—or even voice notes—and get matches and checklists. If they reply 'REMIND' or 'APPLIED', confirm their reminder date and send the official status link. Make sure we verify incoming requests and never send duplicate replies.
2.	Live Voice on the Web: Upgrade our web mic button to real-time voice conversation (using LiveKit and Sarvam) where she can interrupt [BARGE] the AI mid-sentence, hear short natural replies under 35 words, and still see the full cards on screen.

 the voice agent must sound like a real phone conversation- it should allow user to talk-respond-if user asks or speaks something in middle , you must stop to listen and answer. must be like a phone conversation.

while user speaking the voice chunks must be appear in the text box ,live streaming of chunks
How should we plug both of these into what we've already built without breaking the core app?" 
Prompt 10: Testing Everything Before Launch
"Before we call this done, let's make sure everything actually works and our safety promises hold up. Figure out a solid automated test suite that checks our privacy filter (making sure all ID formats get hidden), tests all 4 sample profiles against the right lanes and conflict alerts, checks that 'Guaranteed' never appears anywhere, tests our login/role security, and verifies the admin approval flow. Let's run it and fix anything that breaks."

