I'm Boris and I created Claude Code. Lots of people have asked how I use Claude Code, so I wanted to show off my setup a bit.

My setup might be surprisingly vanilla! Claude Code works great out of the box, so I personally don't customize it much. There is no one correct way to use Claude Code: we intentionally build it in a way that you can use it, customize it, and hack it however you like. Each person on the Claude Code team uses it very differently.
·
Jan 2
1/ I run 5 Claudes in parallel in my terminal. I number my tabs 1-5, and use system notifications to know when a Claude needs input https://code.claude.com/docs/en/terminal-config#iterm-2-system-notifications
Boris Cherny
@bcherny
·
Jan 2
2/ I also run 5-10 Claudes on http://claude.ai/code, in parallel with my local Claudes. As I code in my terminal, I will often hand off local sessions to web (using &), or manually kick off sessions in Chrome, and sometimes I will --teleport back and forth. I also start a few sessions from my phone (from the Claude iOS app) every morning and throughout the day, and check in on them later.
·
Jan 2
3/ I use Opus 4.5 with thinking for everything. It's the best coding model I've ever used, and even though it's bigger & slower than Sonnet, since you have to steer it less and it's better at tool use, it is almost always faster than using a smaller model in the end.
Boris Cherny
@bcherny
·
Jan 2
4/ Our team shares a single http://CLAUDE.md for the Claude Code repo. We check it into git, and the whole team contributes multiple times a week. Anytime we see Claude do something incorrectly we add it to the http://CLAUDE.md, so Claude knows not to do it next time.

Other teams maintain their own http://CLAUDE.md's. It is each team's job to keep theirs up to date.
·
Jan 2
5/ During code review, I will often tag @.claude on my coworkers' PRs to add something to the http://CLAUDE.md as part of the PR. We use the Claude Code Github action (/install-github-action) for this. It's our version of 
@danshipper
's Compounding Engineering

Boris Cherny
@bcherny
·
Jan 2
6/ Most sessions start in Plan mode (shift+tab twice). If my goal is to write a Pull Request, I will use Plan mode, and go back and forth with Claude until I like its plan. From there, I switch into auto-accept edits mode and Claude can usually 1-shot it. A good plan is really important!
·
Jan 2
7/ I use slash commands for every "inner loop" workflow that I end up doing many times a day. This saves me from repeated prompting, and makes it so Claude can use these workflows, too. Commands are checked into git and live in .claude/commands/.

For example, Claude and I use a /commit-push-pr slash command dozens of times every day. The command uses inline bash to pre-compute git status and a few other pieces of info to make the command run quickly and avoid back-and-forth with the model (https://code.claude.com/docs/en/slash-commands#bash-command-execution)
·
Jan 2
8/ I use a few subagents regularly: code-simplifier simplifies the code after Claude is done working, verify-app has detailed instructions for testing Claude Code end to end, and so on. Similar to slash commands, I think of subagents as automating the most common workflows that I do for most PRs.
·
Jan 2
9/ We use a PostToolUse hook to format Claude's code. Claude usually generates well-formatted code out of the box, and the hook handles the last 10% to avoid formatting errors in CI later.
10/ I don't use --dangerously-skip-permissions. Instead, I use /permissions to pre-allow common bash commands that I know are safe in my environment, to avoid unnecessary permission prompts. Most of these are checked into .claude/settings.json and shared with the team.
Boris Cherny
@bcherny
·
Jan 2
11/ Claude Code uses all my tools for me. It often searches and posts to Slack (via the MCP server), runs BigQuery queries to answer analytics questions (using bq CLI), grabs error logs from Sentry, etc. The Slack MCP configuration is checked into our .mcp.json and shared with the team.
·
Jan 2
12/ For very long-running tasks, I will either (a) prompt Claude to verify its work with a background agent when it's done, (b) use an agent Stop hook to do that more deterministically, or (c) use the ralph-wiggum plugin (originally dreamt up by 
@GeoffreyHuntley
). I will also use either --permission-mode=dontAsk or --dangerously-skip-permissions in a sandbox to avoid permission prompts for the session, so Claude can cook without being blocked on me.

·
Jan 2
13/ A final tip: probably the most important thing to get great results out of Claude Code -- give Claude a way to verify its work. If Claude has that feedback loop, it will 2-3x the quality of the final result.

Claude tests every single change I land to http://claude.ai/code using the Claude Chrome extension. It opens a browser, tests the UI, and iterates until the code works and the UX feels good.

Verification looks different for each domain. It might be as simple as running a bash command, or running a test suite, or testing the app in a browser or phone simulator. Make sure to invest in making this rock-solid.

https://code.claude.com/docs/en/chrome

---

The complete claude code tutorial 
I’ve been a SWE for 7 years, between Amazon, Disney, and Capital One. The code I’ve shipped touches millions of users, and I built systems that couldn’t afford to break. Now I’m the CTO of a startup that builds agents for enterprise, and Claude Code is my daily driver.
Here’s a beginners playbook you might find useful, containing everything I’ve learned about Claude after using it to build robust systems that handle complex workloads from large companies. Let me know if it helps below.
Think First
Most people assume that with Claude Code and other AI tools, the first thing you need to do is type (or start talking). But that's probably one of the biggest mistakes that you can make straight off the bat. The first thing that you actually need to do is think.
10 out of 10 times, the output I've gotten with plan mode did significantly better than when I just started talking and spewing everything into Claude Code. It's not even close.
Now for some of you, this is easier said than done. You might not have years of software engineering experience that would allow you to think about this on your own. To this extent I have two pieces of advice:
1. Start learning. You are handicapping yourself if you never pick up on this, even if just a little bit at a time.
2. Have a deep back and forth with ChatGPT/Gemini/Claude, where you describe exactly what you want to build, you ask the LLM for the various options you can take in terms of system design, and ultimately the two of you settle on a solution. You and the LLM should be asking each other questions, not just a one way street. .
This applies to everything. This also includes very small tasks like summarizing emails. Before you ask Claude to build a feature, think about the architecture. Before you ask it to refactor something, think about what the end state should look like. Before you ask it to debug, think about what you actually know about the problem. The more information that you have in plan mode, the better your output is actually going to be because the better the input is going to be.
The pattern is consistent: thinking first, then typing, produces dramatically better results than typing first and hoping Claude figures it out.
This brings me onto my next point of architecture. Architecture, especially in software engineering, is a little bit like giving a person the output and nothing more. This leaves for A LOT of wiggle room in how to get to the output, which is essentially what the problem with AI generated code is. If you say something super broad like “build me an auth system” as opposed to “Build email/password authentication using the existing User model, store sessions in Redis with 24-hour expiry, and add middleware that protects all routes under /api/protected.”, you can see the difference.
You click shift + tab twice, and you’re in plan mode. Trust me when I say this, this is going to take 5 minutes of your time, but will save you hours upon hours of debugging later on.
CLAUDE.md
CLAUDE.md is a markdown file. Markdown is a text format that AI models process extremely well, and Claude in particular handles it better than most other models I've tested.
When you start a Claude Code session, the first thing Claude does is read your CLAUDE.md file. Every instruction in that file shapes how Claude approaches your project. It's essentially onboarding material that Claude reads before every single conversation.
Most people either ignore it completely or stuff it with garbage that makes Claude worse instead of better. There is a threshold where too much or too little information means worse model output.
Here's what actually matters:
Keep it short. Claude can only reliably follow around 150 to 200 instructions at a time, and Claude Code's system prompt already uses about 50 of those. Every instruction you add competes for attention. If your CLAUDE.md is a novel, Claude will start ignoring things randomly and you won't know which things.
Make it specific to your project. Don't explain what a components folder is. Claude knows what components are. Tell it the weird stuff, like the bash commands that actually matter. Everything that is part of your flow should go into it.
Tell it why, not just what. Claude is a little bit like a human in this way. When you give it the reason behind an instruction, Claude implements it better than if you just tell it what to do. "Use TypeScript strict mode" is okay. "Use TypeScript strict mode because we've had production bugs from implicit any types" is better. The why gives Claude context for making judgment calls you didn't anticipate. You'll be surprised how effective this actually is.
Update it constantly. Press the # key while you're working and Claude will add instructions to your CLAUDE.md automatically. Every time you find yourself correcting Claude on the same thing twice, that's a signal it should be in the file. Over time your CLAUDE.md becomes a living document of how your codebase actually works.
Bad CLAUDE.md looks like documentation written for a new hire. Good CLAUDE.md looks like notes you'd leave yourself if you knew you'd have amnesia tomorrow.
The Limitations of Context Windows
For example, Opus 4.5 has a 200,000 token context window. But here's what most people don't realize: the model starts to deteriorate way before you hit 100%. (this is varying dependent on whether you use through API vs desktop app)
At around 20-40% context usage is where the quality of the output starts to chip away, even if not significantly.  If you've ever experienced Claude Code compacting and then still giving you terrible output afterwards, that's why. The model was already degraded before the compaction happened, and compaction doesn't magically restore quality. (hit /compact for compacting)
Every message you send, every file Claude reads, every piece of code it generates, every tool result - all of it accumulates. And once quality starts dropping, more context makes it worse, not better. So here are some things that actually help with not having terrible context
Scope your conversations. One conversation per feature or task. Don't use the same conversation to build your auth system and then also refactor your database layer. The contexts will bleed together and Claude will get confused. I know at least one of you reading this is guilty of that.
Use external memory. If you're working on something complex, have Claude write plans and progress to actual files (I use SCRATCHPAD.md or plan.md). These persist across sessions. When you come back tomorrow, Claude can read the file and pick up where you left off instead of starting from zero. Sidenote: if you have a hierarchy system of files, keeping these at thievery top is how you can get these to work for every task / feature that you decide to build out.
The copy-paste reset. This is a trick I use constantly. When context gets bloated, I copy everything important from the terminal, run /compact to get a summary, then /clear the context entirely, and paste back in only what matters. Fresh context with the critical information preserved. Way better than letting Claude struggle through degraded context.
Know when to clear. If a conversation has gone off the rails or accumulated a bunch of irrelevant context, just /clear and start fresh. It's better than trying to work through confusion. Claude will still have your CLAUDE.md, so you're not losing your project context. Nine times out of ten, using clear is actually better than not using it, as counterintuitive as that sounds.
The mental model that works: Claude is stateless. Every conversation starts from nothing except what you explicitly give it. Plan accordingly.
Prompts Are Everything
People spend weeks learning frameworks and tools. They spend zero time learning how to communicate with the thing that's actually generating their code.
Prompting isn't some mystical art. It’s probably the most fundamental form of communication there is. And like any communication, being clear gets you better results than being vague. Every. Single. Time.
What actually helps:
Be specific about what you want. "Build an auth system" gives Claude creative freedom it will use poorly. "Build email/password authentication using this existing User model, store sessions in Redis, and add middleware that protects routes under /api/protected" gives Claude a clear target. Even this is still not perfect.
Tell it what NOT to do. Claude has tendencies. Claude 4.5 in particular likes to overengineer - extra files, unnecessary abstractions, flexibility you didn't ask for. If you want something minimal, say "Keep this simple. Don't add abstractions I didn't ask for. One file if possible." Also, always cross-reference what Claude produces because you don't want to end up having technical debt, especially if you're building something super simple and it ends up building 12 different files for a task that realistically could have been fixed with a couple of lines of code.
Something that you have to remember is that AI is designed to speed us up and not completely replace us, especially in the era of very professional software engineering. Claude still makes mistakes. I'm sure that it will keep making mistakes, even if it's going to get better over time. So being able to recognize these mistakes will actually solve a lot of your problems.
Give it context about why. "We need this to be fast because it runs on every request" changes how Claude approaches the problem. "This is a prototype we'll throw away" changes what tradeoffs make sense. Claude can't read your mind about constraints you haven't mentioned.
Remember: output is everything, but it only comes from input. If your output sucks, your input sucked. There's no way around this.
Bad Input == Bad Output
People blame the model when they get bad results. "Claude isn't smart enough" or "I need a better model."
Reality check: you suck. If you're getting bad output with a good model like Opus 4.5, that means your input and your prompting sucks. Full stop.
The model matters. A lot, actually. But model quality is table stakes at this point. The bottleneck is almost always on the human side: how you structure your prompts, how you provide context, how clearly you communicate what you actually want.
If you're consistently getting bad results, the fix isn't switching models. The fix is getting better at:
How you write prompts. Specific > vague. Constraints > open-ended. Examples > descriptions.
How you structure requests. Break complex tasks into steps. Get agreement on architecture before implementation. Review outputs and iterate.
How you provide context. What does Claude need to know to do this well? What assumptions are you making that Claude can't see?
That said, there are real differences between models:
Sonnet is faster and cheaper. It's excellent for execution tasks where the path is clear - writing boilerplate, refactoring based on a specific plan, implementing features where you've already made the architectural decisions.
Opus is slower and more expensive. It's better for complex reasoning, planning, and tasks where you need Claude to think deeply about tradeoffs.
A workflow that works: use Opus to plan and make architectural decisions, then switch to Sonnet (Shift+Tab in Claude Code) for implementation. This will depend on your task, sometimes you can use opus 4.5 for implementation as well. Think about selling your kidney if you’re doing this through the API usage tab though. Your CLAUDE.md ensures both models operate under the same constraints, so the handoff is clean.
MCP, Tools, and Configurations
Claude has a ridiculous amount of features. MCP servers. Hooks. Custom slash commands. Settings.json configurations. Skills. Plugins.
You don't need all of them. But you should actually try them and experiment, because if you're not experimenting, you're probably leaving time or money on the table. I promise you there's at least one new feature coming out in Claude that you don't know about, that you can actually learn about if you follow Boris, the founder of Claude Code.
MCP (Model Context Protocol) lets Claude connect to external services. Slack, GitHub, databases, APIs. If you find yourself constantly copying information from one place into Claude, there's probably an MCP server that can do it automatically. There's a ton of MCP marketplaces, and if there is not an MCP, it's just a way of getting structured data, so you can just create your own MCP server for whatever tool that you need added that doesn't exist at the moment. I will be very surprised if you find one that doesn't exist though.
Hooks let you run code automatically before or after Claude makes changes. Want Prettier to run on every file Claude touches? Hook. Want type checking after every edit? Hook. This catches problems immediately instead of letting them pile up. This is actually what helps remove technical debt as well. If you set a specific hook after every thousand lines, you have the security feature potentially cleaning up your code. Should be very helpful when Claude reviews your PRs.
Custom slash commands are just prompts you use repeatedly, packaged as commands. Create a .claude/commands folder, add markdown files with your prompts, and now you can run them with /commandname. If you're running the same kind of task often - debugging, reviewing, deploying - make it a command.
If you have the Pro Max plan (I pay the $200/month), why not try everything Claude has to offer? See what works and what doesn't. You're paying for it anyway.
And here's the thing: don't get shut off if something doesn't work on the first try. These models are improving basically every week. Something that didn't work a month ago might work now. Being an early adopter means staying curious and re-testing things.
When Claude Gets Stuck
Sometimes Claude just loops. It tries the same thing, fails, tries again, fails, and keeps going. Or it confidently implements something that's completely wrong and you spend twenty minutes trying to explain why.
When this happens, the instinct is to keep pushing. More instructions. More corrections. More context. But the reality is that the better move is just to change the approach entirely.
Start off simple - clear the conversation. The accumulated context might be confusing it. /clear gives you a fresh start.
Simplify the task. If Claude is struggling with a complex task, break it into smaller pieces. Get each piece working before combining them. But in reality, if Claude is struggling with a complex task, that means that your plan mode is insufficient.
Show instead of tell. If Claude keeps misunderstanding what you want, write a minimal example yourself. "Here's what the output should look like. Now apply this pattern to the rest." Claude is extremely good at understanding what success metrics look like and actually being able to follow them, of what a good example is.
Be creative. Try a different angle. Sometimes the way you framed the problem doesn't map well to how Claude thinks. Reframing - "implement this as a state machine" vs "handle these transitions" - can unlock progress.
The meta-skill here is recognizing when you're in a loop early. If you've explained the same thing three times and Claude still isn't getting it, more explaining won't help. Change something.
Build Systems
The people who get the most value from Claude aren't using it for one-off tasks. They're building systems where Claude is a component. But claude code is way better than that. It has a -p flag for headless mode. It runs your prompt and outputs the result without entering the interactive interface. This means you can script it. Pipe output to other tools. Chain it with bash commands. Integrate it into automated workflows.
Enterprises are using this for automatic PR reviews, automatic support ticket responses, automatic logging and documentation updates. All of it logged, auditable, and improving over time based on what works and what doesn't.
The flywheel: Claude makes a mistake, you review the logs, you improve the CLAUDE.md or tooling, Claude gets better next time. This compounds. Right now I'm in the process of being able to have Claude already improve its own Claude.md files though. After months of iteration, systems built this way are meaningfully better than they were at launch - same models, just better configured.
If you're only using Claude interactively, you're leaving value on the table. Think about where in your workflow Claude could run without you watching.
TLDR
Think before you type. Planning produces dramatically better results than just starting to talk.
CLAUDE.md is your leverage point. Keep it short, specific, tell it why, and update constantly. This single file affects every interaction.
Context degrades at 30%, not 100%. Use external memory, scope conversations, and don't be afraid to clear and restart with the copy-paste reset trick.
Architecture matters more than anything. You cannot skip planning. If you don't think through structure first, output will be bad.
Output comes from input. If you're getting bad results with a good model, your prompting needs work. Get better at communicating.
Experiment with tools and configuration. MCP, hooks, slash commands. If you're paying for Pro Max, try everything. Stay curious even when things don't work the first time.
When stuck, change the approach. Don't loop. Clear, simplify, show, reframe.
Build systems, not one-shots. Headless mode, automation, logged improvements over time.
If you're building with Claude - whether it's your own projects or production systems - these are the things that determine whether you're fighting the tool or flowing with it.
Modern day technology is absurdly capable. If you want more tips on how to get the most out of AI for yourself or your business, subscribe to my free weekly AI newsletter: https://varickagents.com/newsletter
Want to publish your own Article?
Upgrade to Premium
8:51 PM · Jan 10, 2026
·

---

The Shorthand Guide to Everything Claude Code
Here's my complete setup after 10 months of daily use: skills, hooks, subagents, MCPs, plugins, and what actually works.
Been an avid Claude Code user since the experimental rollout in Feb, and won the Anthropic x Forum Ventures hackathon with Zenith alongside @DRodriguezFX completely using Claude Code. 
cogsec
@affaanmustafa
·
Sep 16, 2025
took the W at the 
@AnthropicAI
 x 
@forumventures
 hackathon in NYC

thanks for hosting guys was a great event (and for the 15k in Anthropic Credits)

@DRodriguezFX
 and I built PMFProbe to take founders from 0 -> 1, validate your idea at the pre MVP stage

more to come soon
Skills and Commands
Skills operate like rules, constricted to certain scopes and workflows. They're shorthand to prompts when you need to execute a particular workflow.
After a long session of coding with Opus 4.5, you want to clean out dead code and loose .md files? 
Run /refactor-clean. Need testing? /tdd, /e2e, /test-coverage. Skills and commands can be chained together in a single prompt
chaining commands together
I can make a skill that updates codemaps at checkpoints - a way for Claude to quickly navigate your codebase without burning context on exploration.
~/.claude/skills/codemap-updater.md
Commands are skills executed via slash commands. They overlap but are stored differently:
Skills: ~/.claude/skills - broader workflow definitions
Commands: ~/.claude/commands - quick executable prompts
bash
# Example skill structure
~/.claude/skills/
  pmx-guidelines.md      # Project-specific patterns
  coding-standards.md    # Language best practices
  tdd-workflow/          # Multi-file skill with README.md
  security-review/       # Checklist-based skill
Hooks
Hooks are trigger-based automations that fire on specific events. Unlike skills, they're constricted to tool calls and lifecycle events.
Hook Types
PreToolUse  - Before a tool executes (validation, reminders)
PostToolUse - After a tool finishes (formatting, feedback loops)
UserPromptSubmit - When you send a message
Stop - When Claude finishes responding
PreCompact - Before context compaction
Notification - Permission requests
Example: tmux reminder before long-running commands
json
{
  "PreToolUse": [
    {
      "matcher": "tool == \"Bash\" && tool_input.command matches \"(npm|pnpm|yarn|cargo|pytest)\"",
      "hooks": [
        {
          "type": "command",
          "command": "if [ -z \"$TMUX\" ]; then echo '[Hook] Consider tmux for session persistence' >&2; fi"
        }
      ]
    }
  ]
}
Example of what feedback you get in Claude Code, while running a PostToolUse hook
Pro tip: Use the `hookify` plugin to create hooks conversationally instead of writing JSON manually. Run /hookify and describe what you want.
Subagents
Subagents are processes your orchestrator (main Claude) can delegate tasks to with limited scopes. They can run in background or foreground, freeing up context for the main agent.
Subagents work nicely with skills - a subagent capable of executing a subset of your skills can be delegated tasks and use those skills autonomously. They can also be sandboxed with specific tool permissions.
bash
# Example subagent structure
~/.claude/agents/
  planner.md           # Feature implementation planning
  architect.md         # System design decisions
  tdd-guide.md         # Test-driven development
  code-reviewer.md     # Quality/security review
  security-reviewer.md # Vulnerability analysis
  build-error-resolver.md
  e2e-runner.md
  refactor-cleaner.md
Configure allowed tools, MCPs, and permissions per subagent for proper scoping.
Rules and Memory
Your `.rules` folder holds `.md` files with best practices Claude should ALWAYS follow. Two approaches:
Single CLAUDE.md - Everything in one file (user or project level)
Rules folder - Modular `.md` files grouped by concern
bash
~/.claude/rules/
  security.md      # No hardcoded secrets, validate inputs
  coding-style.md  # Immutability, file organization
  testing.md       # TDD workflow, 80% coverage
  git-workflow.md  # Commit format, PR process
  agents.md        # When to delegate to subagents
  performance.md   # Model selection, context management
Example rules: 
No emojis in codebase
Refrain from purple hues in frontend
Always test code before deployment
Prioritize modular code over mega-files
Never commit console.logs
MCPs (Model Context Protocol)
MCPs connect Claude to external services directly. Not a replacement for APIs - it's a prompt-driven wrapper around them, allowing more flexibility in navigating information.
Example: Supabase MCP lets Claude pull specific data, run SQL directly upstream without copy-paste. Same for databases, deployment platforms, etc.
Example of the supabase mcp listing the tables within the public schema
Chrome in Claude: is a built-in plugin MCP that lets Claude autonomously control your browser - clicking around to see how things work.
CRITICAL: Context Window Management
Be picky with MCPs. I keep all MCPs in user config but disable everything unused. Navigate to /plugins and scroll down or run /mcp.
Your 200k context window before compacting might only be 70k with too many tools enabled. Performance degrades significantly.
using /plugins to navigate to MCPs to see which ones are currently installed and their status 
Rule of thumb: Have 20-30 MCPs in config, but keep under 10 enabled / under 80 tools active.
Plugins
Plugins package tools for easy installation instead of tedious manual setup. A plugin can be a skill + MCP combined, or hooks/tools bundled together.
Installing plugins: 
bash
# Add a marketplace
claude plugin marketplace add https://github.com/mixedbread-ai/mgrep

# Open Claude, run /plugins, find new marketplace, install from there
displaying the newly installed Mixedbread-Grep marketplace
LSP Plugins: are particularly useful if you run Claude Code outside editors frequently. Language Server Protocol gives Claude real-time type checking, go-to-definition, and intelligent completions without needing an IDE open.
bash
# Enabled plugins example
typescript-lsp@claude-plugins-official  # TypeScript intelligence
pyright-lsp@claude-plugins-official     # Python type checking
hookify@claude-plugins-official         # Create hooks conversationally
mgrep@Mixedbread-Grep                   # Better search than ripgrep
Same warning as MCPs - watch your context window.
Tips and Tricks
Keyboard Shortcuts
Ctrl+U - Delete entire line (faster than backspace spam)
! - Quick bash command prefix
@ - Search for files
/ - Initiate slash commands
Shift+Enter - Multi-line input
Tab - Toggle thinking display
Esc Esc - Interrupt Claude / restore code
Parallel Workflows
/fork - Fork conversations to do non-overlapping tasks in parallel instead of spamming queued messages
Git Worktrees - For overlapping parallel Claudes without conflicts. Each worktree is an independent checkout
bash
git worktree add ../feature-branch feature-branch
# Now run separate Claude instances in each worktree
tmux for Long-Running Commands: Stream and watch logs/bash processes Claude runs.

letting claude code spin up the frontend and backend servers and monitoring the logs by attaching to the session using tmux
bash
tmux new -s dev
# Claude runs commands here, you can detach and reattach
tmux attach -t dev
mgrep > grep: `mgrep` is a significant improvement from ripgrep/grep. Install via plugin marketplace, then use the /mgrep skill. Works with both local search and web search.
bash
mgrep "function handleSubmit"  # Local search
mgrep --web "Next.js 15 app router changes"  # Web search
Other Useful Commands
/rewind - Go back to a previous state
/statusline - Customize with branch, context %, todos
/checkpoints - File-level undo points
/compact - Manually trigger context compaction
GitHub Actions CI/CD
Set up code review on your PRs with GitHub Actions. Claude can review PRs automatically when configured.
claude approving a bug fix PR
Sandboxing
Use sandbox mode for risky operations - Claude runs in restricted environment without affecting your actual system. (Use --dangerously-skip-permissions - to do the opposite of this and let claude roam free, this can be destructive if not careful.)
On Editors
While an editor isn't needed it can positively or negatively impact your Claude Code workflow. While Claude Code works from any terminal, pairing it with a capable editor unlocks real-time file tracking, quick navigation, and integrated command execution.
Zed (My Preference)
I use Zed - a Rust-based editor that's lightweight, fast, and highly customizable.
Why Zed works well with Claude Code:
Agent Panel Integration - Zed's Claude integration lets you track file changes in real-time as Claude edits. Jump between files Claude references without leaving the editor
Performance - Written in Rust, opens instantly and handles large codebases without lag
CMD+Shift+R Command Palette - Quick access to all your custom slash commands, debuggers, and tools in a searchable UI. Even if you just want to run a quick command without switching to terminal
Minimal Resource Usage - Won't compete with Claude for system resources during heavy operations
Vim Mode - Full vim keybindings if that's your thing
Zed Editor with custom commands dropdown using CMD+Shift+R.

Following mode shown as the bullseye in the bottom right.
Split your screen - Terminal with Claude Code on one side, editor on the other using 
Ctrl + G  - quickly open the file Claude is currently working on in Zed
Auto-save - Enable autosave so Claude's file reads are always current
Git integration - Use editor's git features to review Claude's changes before committing
File watchers - Most editors auto-reload changed files, verify this is enabled
VSCode / Cursor
This is also a viable choice and works well with Claude Code. You can use it in either terminal format, with automatic sync with your editor using \ide enabling LSP functionality (somewhat redundant with plugins now). Or you can opt for the extension which is more integrated with the Editor and has a matching UI.
from the docs directly at https://code.claude.com/docs/en/vs-code
My Setup
Plugins
Installed: (I usually only have 4-5 of these enabled at a time)
markdown
ralph-wiggum@claude-code-plugins       # Loop automation
frontend-design@claude-code-plugins    # UI/UX patterns
commit-commands@claude-code-plugins    # Git workflow
security-guidance@claude-code-plugins  # Security checks
pr-review-toolkit@claude-code-plugins  # PR automation
typescript-lsp@claude-plugins-official # TS intelligence
hookify@claude-plugins-official        # Hook creation
code-simplifier@claude-plugins-official
feature-dev@claude-code-plugins
explanatory-output-style@claude-code-plugins
code-review@claude-code-plugins
context7@claude-plugins-official       # Live documentation
pyright-lsp@claude-plugins-official    # Python types
mgrep@Mixedbread-Grep                  # Better search
MCP Servers
Configured (User Level):
json
{
  "github": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] },
  "firecrawl": { "command": "npx", "args": ["-y", "firecrawl-mcp"] },
  "supabase": {
    "command": "npx",
    "args": ["-y", "@supabase/mcp-server-supabase@latest", "--project-ref=YOUR_REF"]
  },
  "memory": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"] },
  "sequential-thinking": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
  },
  "vercel": { "type": "http", "url": "https://mcp.vercel.com" },
  "railway": { "command": "npx", "args": ["-y", "@railway/mcp-server"] },
  "cloudflare-docs": { "type": "http", "url": "https://docs.mcp.cloudflare.com/mcp" },
  "cloudflare-workers-bindings": {
    "type": "http",
    "url": "https://bindings.mcp.cloudflare.com/mcp"
  },
  "cloudflare-workers-builds": { "type": "http", "url": "https://builds.mcp.cloudflare.com/mcp" },
  "cloudflare-observability": {
    "type": "http",
    "url": "https://observability.mcp.cloudflare.com/mcp"
  },
  "clickhouse": { "type": "http", "url": "https://mcp.clickhouse.cloud/mcp" },
  "AbletonMCP": { "command": "uvx", "args": ["ableton-mcp"] },
  "magic": { "command": "npx", "args": ["-y", "@magicuidesign/mcp@latest"] }
}
Disabled per project (context window management):
markdown
# In ~/.claude.json under projects.[path].disabledMcpServers
disabledMcpServers: [
  "playwright",
  "cloudflare-workers-builds",
  "cloudflare-workers-bindings",
  "cloudflare-observability",
  "cloudflare-docs",
  "clickhouse",
  "AbletonMCP",
  "context7",
  "magic"
]
This is the key - I have 14 MCPs configured but only ~ 5-6 enabled per project. Keeps context window healthy.
Key Hooks
json
{
  "PreToolUse": [
    // tmux reminder for long-running commands
    { "matcher": "npm|pnpm|yarn|cargo|pytest", "hooks": ["tmux reminder"] },
    // Block unnecessary .md file creation
    { "matcher": "Write && .md file", "hooks": ["block unless README/CLAUDE"] },
    // Review before git push
    { "matcher": "git push", "hooks": ["open editor for review"] }
  ],
  "PostToolUse": [
    // Auto-format JS/TS with Prettier
    { "matcher": "Edit && .ts/.tsx/.js/.jsx", "hooks": ["prettier --write"] },
    // TypeScript check after edits
    { "matcher": "Edit && .ts/.tsx", "hooks": ["tsc --noEmit"] },
    // Warn about console.log
    { "matcher": "Edit", "hooks": ["grep console.log warning"] }
  ],
  "Stop": [
    // Audit for console.logs before session ends
    { "matcher": "*", "hooks": ["check modified files for console.log"] }
  ]
}
Custom Status Line
Shows user, directory, git branch with dirty indicator, context remaining %, model, time, and todo count:
example statusline in my Mac root directory
Rules Structure
markdown
~/.claude/rules/
  security.md      # Mandatory security checks
  coding-style.md  # Immutability, file size limits
  testing.md       # TDD, 80% coverage
  git-workflow.md  # Conventional commits
  agents.md        # Subagent delegation rules
  patterns.md      # API response formats
  performance.md   # Model selection (Haiku vs Sonnet vs Opus)
  hooks.md         # Hook documentation
Subagents
markdown
~/.claude/agents/
  planner.md           # Break down features
  architect.md         # System design
  tdd-guide.md         # Write tests first
  code-reviewer.md     # Quality review
  security-reviewer.md # Vulnerability scan
  build-error-resolver.md
  e2e-runner.md        # Playwright tests
  refactor-cleaner.md  # Dead code removal
  doc-updater.md       # Keep docs synced
Key Takeaways
Don't overcomplicate - treat configuration like fine-tuning, not architecture
Context window is precious - disable unused MCPs and plugins
Parallel execution - fork conversations, use git worktrees
Automate the repetitive - hooks for formatting, linting, reminders
Scope your subagents - limited tools = focused execution
References
- Plugins Reference
- Hooks Documentation
- Checkpointing
- Interactive Mode
- Memory System
- [Subagents]
- [MCP Overview]
Note: This is a subset of detail. I might make more posts on specifics if people are interested.


---

spec. md
Plaintext
@docs/spec.md If you were to break this project down into sprints and tasks, how would you do it (timeline info does not need included and doesnt matter) - every task/ticket should be an atomic, commitable peice of work with tests (and if tests don't make sense another form of validatation that it was completed successfully), every sprint should result in a demoable peice of software that can be run, tested, and build ontop of previous work/sprints. Be exhaustive, be clear, be technical, always focus on small atomic tasks that compose up into a clear goal for the sprint.
Once you're done, provide this prompt to a subagent to review your work and suggest improvements. When you're done reviewing the suggest improvements write your tasks/tickets, sprint plans, etc to a md file.