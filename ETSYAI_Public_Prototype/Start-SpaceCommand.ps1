# Instance SpaceCommand Launcher
# Local-only launcher for SpaceCommand room agents.
# This script only runs Python agent runners inside:
# Uses the folder this script is launched from. No hardcoded user path.
#
# Upgrade:
# - Automatically uses each agent's save flag.
# - Allows custom save titles.
# - Optionally sends the completed run to Sentinel for local QA review.

$Root = $PSScriptRoot
$Core = Join-Path $Root "_core"

$Agents = @(
    @{
        Number = 1
        Name = "Command"
        Room = "00_Bridge"
        Runner = "run_command.py"
        SaveFlag = "--save-plan"
        DefaultTitle = "Launcher Command Plan"
        Description = "Bridge coordination, task queues, room status"
        ReviewType = "Bridge coordination plan"
    },
    @{
        Number = 2
        Name = "Nova"
        Room = "01_ResearchLab"
        Runner = "run_nova.py"
        SaveFlag = "--save-brief"
        DefaultTitle = "Launcher Nova Brief"
        Description = "Research briefs and niche ideas"
        ReviewType = "research brief"
    },
    @{
        Number = 3
        Name = "Forge"
        Room = "02_ForgeFactory"
        Runner = "run_forge.py"
        SaveFlag = "--save-concept"
        DefaultTitle = "Launcher Forge Concept"
        Description = "Concepts, visual direction, design prompts"
        ReviewType = "design concept"
    },
    @{
        Number = 4
        Name = "Scribe"
        Room = "03_ListingRoom"
        Runner = "run_scribe.py"
        SaveFlag = "--save-spec"
        DefaultTitle = "Launcher Scribe Spec"
        Description = "Specs, dashboard copy, build requirements"
        ReviewType = "written specification"
    },
    @{
        Number = 5
        Name = "Sentinel"
        Room = "04_QARoom"
        Runner = "run_sentinel.py"
        SaveFlag = "--save-review"
        DefaultTitle = "Launcher Sentinel Review"
        Description = "QA review and approval gate"
        ReviewType = "Sentinel review"
    },
    @{
        Number = 6
        Name = "Archivist"
        Room = "05_Archives"
        Runner = "run_archivist.py"
        SaveFlag = "--save-memory"
        DefaultTitle = "Launcher Archivist Memory"
        Description = "Memory, decisions, feedback, lessons"
        ReviewType = "memory entry"
    },
    @{
        Number = 7
        Name = "Ledger"
        Room = "06_Treasury"
        Runner = "run_ledger.py"
        SaveFlag = "--save-report"
        DefaultTitle = "Launcher Ledger Report"
        Description = "Costs, budget, tool spending notes"
        ReviewType = "cost or budget report"
    },
    @{
        Number = 8
        Name = "Strategist"
        Room = "07_WarRoom"
        Runner = "run_strategist.py"
        SaveFlag = "--save-review"
        DefaultTitle = "Launcher Strategist Review"
        Description = "WarRoom reviews and next missions"
        ReviewType = "WarRoom strategy review"
    },
    @{
        Number = 9
        Name = "Smith"
        Room = "08_Armory"
        Runner = "run_smith.py"
        SaveFlag = "--save-blueprint"
        DefaultTitle = "Launcher Smith Blueprint"
        Description = "Tools, scripts, safety blueprints"
        ReviewType = "Armory tool or automation blueprint"
    },
    @{
        Number = 10
        Name = "Signal"
        Room = "09_MediaBay"
        Runner = "run_signal.py"
        SaveFlag = "--save-package"
        DefaultTitle = "Launcher Signal Package"
        Description = "Media drafts, captions, thumbnail concepts"
        ReviewType = "media package"
    },
    @{
        Number = 11
        Name = "Echo"
        Room = "10_CommsHub"
        Runner = "run_echo.py"
        SaveFlag = "--save-draft"
        DefaultTitle = "Launcher Echo Draft"
        Description = "Communication drafts and templates"
        ReviewType = "communication draft"
    },
    @{
        Number = 12
        Name = "Overseer"
        Room = "_overseer"
        Runner = "run_overseer.py"
        SaveFlag = "--save-mission"
        DefaultTitle = "Launcher Overseer Mission"
        Description = "Planning-only full-system mission orders"
        ReviewType = "Overseer mission order"
    }
)

function Show-Menu {
    Clear-Host
    Write-Host ""
    Write-Host "============================================"
    Write-Host "      INSTANCE SPACECOMMAND LAUNCHER"
    Write-Host "============================================"
    Write-Host ""
    Write-Host "Root: $Root"
    Write-Host "Core: $Core"
    Write-Host ""
    Write-Host "Choose an agent:"
    Write-Host ""

    foreach ($agent in $Agents) {
        Write-Host ("[{0}] {1,-10} - {2}" -f $agent.Number, $agent.Name, $agent.Description)
    }

    Write-Host ""
    Write-Host "[Q] Quit"
    Write-Host ""
}

function Get-AgentBySelection {
    param(
        [string]$Selection
    )

    foreach ($agent in $Agents) {
        if ($Selection -eq [string]$agent.Number) {
            return $agent
        }
    }

    return $null
}

function Get-SafeTitle {
    param(
        [string]$Title,
        [string]$Fallback
    )

    if ([string]::IsNullOrWhiteSpace($Title)) {
        return $Fallback
    }

    $safe = $Title.Trim()

    if ($safe.Length -gt 80) {
        $safe = $safe.Substring(0, 80)
    }

    return $safe
}

function Invoke-SpaceCommandAgent {
    param(
        [hashtable]$Agent,
        [string]$Message,
        [string]$Title
    )

    $runnerPath = Join-Path $Core $Agent.Runner

    if (-not (Test-Path $runnerPath)) {
        Write-Host ""
        Write-Host "ERROR: Runner not found:"
        Write-Host $runnerPath
        return @{
            Success = $false
            Output = ""
        }
    }

    Write-Host ""
    Write-Host "Running $($Agent.Name)..."
    Write-Host ""

    $output = & python $runnerPath $Message $Agent.SaveFlag --title $Title 2>&1
    $exitCode = $LASTEXITCODE

    $outputText = $output -join "`n"

    if (-not [string]::IsNullOrWhiteSpace($outputText)) {
        Write-Host $outputText
    }

    if ($exitCode -ne 0) {
        Write-Host ""
        Write-Host "ERROR: $($Agent.Name) exited with code $exitCode."
        return @{
            Success = $false
            Output = $outputText
        }
    }

    Write-Host ""
    Write-Host "$($Agent.Name) run complete."
    return @{
        Success = $true
        Output = $outputText
    }
}

function Invoke-SentinelReview {
    param(
        [hashtable]$ReviewedAgent,
        [string]$OriginalMessage,
        [string]$Title,
        [string]$AgentOutput
    )

    $sentinelRunner = Join-Path $Core "run_sentinel.py"

    if (-not (Test-Path $sentinelRunner)) {
        Write-Host ""
        Write-Host "ERROR: Sentinel runner not found:"
        Write-Host $sentinelRunner
        return
    }

    $reviewPrompt = @"
Review $($ReviewedAgent.Name)'s latest launcher-run $($ReviewedAgent.ReviewType).

Original user request:
$OriginalMessage

Saved title:
$Title

Actual agent output to review:
$AgentOutput

Review goals:
- Confirm it is local-only and draft-only.
- Check whether it matches the agent's role.
- Check for hallucinated rooms, agents, teams, tools, external actions, fake commands, or false claims.
- Check for safety issues.
- If safe and useful, mark APPROVED.
- If local-only but flawed, mark NEEDS_REVISION.
- Only mark REQUIRES_HUMAN_APPROVAL if it proposes a real external action such as account access, publishing, messaging, buying, selling, scraping, browser automation, payment access, tool installation, or sending data outside the local project.
"@

    Write-Host ""
    Write-Host "Running Sentinel review..."
    Write-Host ""

    python $sentinelRunner $reviewPrompt --save-review

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Sentinel exited with code $LASTEXITCODE."
        return
    }

    Write-Host ""
    Write-Host "Sentinel review complete."
}

if (-not (Test-Path $Core)) {
    Write-Host "ERROR: _core folder not found:"
    Write-Host $Core
    exit 1
}

while ($true) {
    Show-Menu

    $selection = Read-Host "Selection"

    if ($selection.ToLower() -eq "q") {
        Write-Host "Exiting SpaceCommand launcher."
        break
    }

    $agent = Get-AgentBySelection -Selection $selection

    if ($null -eq $agent) {
        Write-Host ""
        Write-Host "Invalid selection."
        Pause
        continue
    }

    $runnerPath = Join-Path $Core $agent.Runner

    if (-not (Test-Path $runnerPath)) {
        Write-Host ""
        Write-Host "ERROR: Runner not found:"
        Write-Host $runnerPath
        Pause
        continue
    }

    Write-Host ""
    Write-Host "Selected: $($agent.Name)"
    Write-Host "Room:     $($agent.Room)"
    Write-Host "Runner:   $runnerPath"
    Write-Host "Save:     $($agent.SaveFlag)"
    Write-Host ""
    Write-Host "This will run a local Python agent runner inside SpaceCommand only."
    Write-Host "The output will be saved using this agent's save flag."
    Write-Host ""

    $message = Read-Host "Enter the message/request for $($agent.Name)"

    if ([string]::IsNullOrWhiteSpace($message)) {
        Write-Host ""
        Write-Host "No message entered. Returning to menu."
        Pause
        continue
    }

    Write-Host ""
    $customTitle = Read-Host "Optional save title, or press Enter for default"
    $title = Get-SafeTitle -Title $customTitle -Fallback $agent.DefaultTitle

    Write-Host ""
    Write-Host "Ready to run:"
    Write-Host "Agent: $($agent.Name)"
    Write-Host "Title: $title"
    Write-Host "Save:  $($agent.SaveFlag)"
    Write-Host ""
    $confirm = Read-Host "Run $($agent.Name) now? Type YES to confirm"

    if ($confirm -ne "YES") {
        Write-Host ""
        Write-Host "Cancelled. Returning to menu."
        Pause
        continue
    }

    $runResult = Invoke-SpaceCommandAgent -Agent $agent -Message $message -Title $title

    if ($runResult.Success -eq $true -and $agent.Name -ne "Sentinel") {
        Write-Host ""
        $reviewChoice = Read-Host "Send this run to Sentinel for review? Type YES to review, or press Enter to skip"

        if ($reviewChoice -eq "YES") {
            Invoke-SentinelReview -ReviewedAgent $agent -OriginalMessage $message -Title $title -AgentOutput $runResult.Output
        }
        else {
            Write-Host "Sentinel review skipped."
        }
    }
    elseif ($agent.Name -eq "Sentinel") {
        Write-Host ""
        Write-Host "Skipping Sentinel auto-review because the selected agent was Sentinel."
    }

    Write-Host ""
    Write-Host "Launcher cycle complete."
    Pause
}


