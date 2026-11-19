# Research retry protocol v2 — 2026-11-16

Purpose: improve both strategy and the experiment loop. A retry is a falsifiable research iteration, not another random seed or an attempt to fit a required return on reused data.

1. Read latest branch reports and running-job/checkpoint state. Do not overwrite another researcher's changes or launch duplicate jobs. Record the input code/data version, exact periods, universe and proxy instruments.
2. Review what failed, and what was ambiguous about the previous experiment. State one mechanism, an explicit comparator, a planned shortlist rule and rejection criteria before execution. Keep a record of hypotheses already rejected. Change the protocol only with a reason, not for novelty.
3. Separate entry, exit, sizing, routing and execution changes. If multiple must change, use ablations. Keep an anchored comparator and cash where appropriate. Never raise exposure or remove protections merely to clear a target.
4. For entry filters, perform BOTH frozen-opportunity attribution and full replay. Attribution partitions the baseline's existing rounds by the information at their original signal index. Its sums/means are not portfolio returns. Replay can change entry timing, risk halts and later opportunities, so report it separately. Baseline logs truncated by a drawdown halt do not represent all latent opportunities.
5. Use completed-bar information, explicit release timestamps and prefix-invariance tests for derived timeframes. Macro/news require actual point-in-time histories. Do not fabricate missing feeds.
6. Choose candidates using development periods and stress tests only. Freeze shortlist before diagnostics. A least-bad winner remains rejected if it fails predeclared criteria. A minimum-round threshold screens tiny samples; it does not prove statistical reliability. Include uncertainty and multiple-testing concerns before promotion.
7. Keep reused 2026 labeled diagnostic. A new filter cannot restore independence to a repeatedly inspected period. Independently confirm on untouched data before any deployment claim. Record costs, delays, borrow/execution limitations, drawdown measurement granularity and true holding horizon.
8. Report net cumulative return with exact dates, drawdown, rounds, win rate, profit factor, baseline delta, cost2 and delay1 separately. Never confuse percentage points with percentages or weekly with cumulative returns. Retain losing trials and raw ranking rather than only winners.
9. Save code/tests/config/manifest/results/report to the authorized development branch. Generated large ledgers can be reproducible local outputs if this is explicitly stated. Leave a concrete next hypothesis and a handoff identifying what ran and what did not.
10. Scheduled runs must report unavailable execution/data access truthfully; never substitute a plan for a completed backtest or claim an ongoing worker after it ended. Real orders remain out of scope.

Initial v2 adoption: `scripts/anchor_filter_audit.py` fixes anchor signal and exits, audits ten single filters plus anchor, requires at least 20 rounds per development scenario for diagnostic eligibility, and requires all six development scenarios positive and each better than anchor for its research promotion screen. These thresholds are this experiment's preregistered rules, not universal statistical assurance. Every candidate failed promotion.

Known protocol weakness to address next: ranking on worst return tends to prefer sparse participation. Pair return improvements with opportunity coverage and confidence, and add new independent periods. Also examine potential code-path effects: gated replay can find opportunities the frozen baseline never executed. Do not infer causality from raw aggregate return differences alone.

2026-11-16 holding retry evidence-based additions:
- Missing raw inputs must be recovered or explicitly versioned as a new data snapshot. Compare its hash before experiments. If different, rerun all comparators and separate data-revision differences from strategy deltas; never silently overwrite archived metrics. Pin the actual CSV when practical.
- Decompose any net improvement into gross leg contributions and costs, using capital-weighted ledger accounting. Fewer rounds and lower costs do not establish improved price-path capture. For exit changes, full replay changes future opportunities and is not a matched-entry causal comparison.
- Latest evidence/handoff: HOLDING_RETRY_REPORT_20261116.md; hold-only top1 rejected across development, despite slightly higher reused-2026 base profit.

2026-11-16 user scope correction — real inverse ETF implementation:
- Research universe now includes actual TQQQ/SQQQ/IBIT/BITI ETF buys. Distinguish a bearish signal, borrowed short sale, and purchase of an inverse ETF. Verify actual per-ticker ledger counts; a ticker present only in downloaded files is not evidence it was traded.
- Isolate instrument implementation from direction logic and timeframe filters. An inverse ETF price path is not the negative spot ETF return; replay actual bars with correct purchase sign and no short borrow charge. Keep capital caps and protective stops, acknowledge differing underlying sensitivity.
- Latest experiment and next handoff: INVERSE_ETF_RETRY_REPORT_20261116.md. All development candidates rejected; next is fixed-cap single-asset participation ablation, not yet run.

2026-11-16 single-asset participation evidence:
- Explicitly select nonzero buy roles for optional participation; do not let zero-score assets become phantom second holdings. Leave unused allocation in cash. Reconcile actual ETF order counts instead of assuming two orders per round.
- A profitable frozen subset in reused2026 is insufficient: report the same subset's development cost/delay stresses and the complete replay separately. Here single-opportunity subsets also failed development stresses, so do not repeat a simple single-only filter based on2026 alone.
- Latest handoff SINGLE_ASSET_RETRY_REPORT_20261116.md: 51 runs, all candidates rejected; next diagnose development forward-path decay as labels, not future information in signals.

2026-11-16 forward-label/exhaustion evidence:
- Compare horizons on a common entry cohort when possible; horizon-specific session truncation changes sample composition. Forward labels are development diagnostics, not entry features or account returns; keep paired actual inverse-ETF paths separate from protected replay.
- Worse original gross paths do not imply a profitable inverse strategy. Full/dual-only/single-only direction swaps were ablated; all rejected, with full inversion failing cost2 in both development halves and losing reused2026. Do not repeat this family without a new mechanism.
- Normalize archived period types before regression checks; report aborted attempts separately. Latest handoff: SIGNAL_DECAY_RETRY_REPORT_20261116.md (39 completed backtests). Next diagnose repeated entries into unchanged states before considering event-onset entries.

2026-11-16 event-onset retry evidence:
- A change in the signal vector is not necessarily new actionable information: disappearing roles alone must not trigger onset entries. Specify the event precisely and test both positive and negative cases.
- Entry gating need not reduce full-replay turnover when stops/cooldowns/account halts alter future opportunities. Report frozen admitted/rejected baseline rounds and full account costs/order counts separately; event gating here increased diagnostic replay costs and lost more money.
- Latest handoff EVENT_ENTRY_RETRY_REPORT_20261116.md:27 completed account runs, all rejected. Next measure exit reasons, gap effects and intraround marks with output-invariance logging before changing exits.

## User-approved broad/adaptive retry workflow (2026-11-16)
A retry now includes an explicitly delegated creative quant review, diverse strategy families and bounded parameter grids, followed by staged development/stress selection and ablations. Default budget64 candidates (4 families×16 parameter settings), at most8 shortlisted candidates; expand only with evidence. Cache old failures; do not substitute endless tiny filter tests for broad research.
Assess recent3/6month windows too: full-window best fits are exploratory in-sample rankings and may matter for regime research despite poor older performance. Separately choose from strictly preceding3/6months and replay the next calendar month, freezing choice before observing that month. Call this causal walk-forward research on reused data, not an untouched holdout. Minimum samples and cost/delay screens apply before selection; cash fallback when none qualifies.
Codex↔Claude coordination: read RETRY_STATE.json and RESEARCH_HANDOFF.md first, use a unique run ID, claim RUNNING with expected branch parent before work, save checkpoints, then COMPLETE with exact reproduction commands/data hashes/results and concrete next actions. Never replace someone else's newer commit or reset others' work. Summarize progress/results briefly; detailed grids and failures belong in CSV/JSON/report.

2026-11-17 continuous account correction:
- Monthly walk-forward portfolio claims must preserve account equity/peak, daily state, loss streak, cooldown and permanent kill across segments. AccountState is optional; use the same MarketData/global indices and flat session-boundary stops. Do not reset a halted account at calendar boundaries.
- Report ever_halted/first halt and actual trade counts, not only final-month killed status. Reduced terminal loss after earlier permanent halt is risk execution, not new alpha. Compare continuity components to isolate causes.
- Latest report CONTINUOUS_RISK_RETRY_REPORT_20261117.md:27 account scenarios/300engine calls;55tests. No new grid fitted in this execution-only correction. Next4creative families and64bounded settings are proposed in runs/continuous_risk_retry_20261117/quant_next_proposals.md, not implemented/tested.

2026-11-17 new OHLCV families:
- Count signal-time entry opportunities as an upper bound before spending attention on sparse-event winners. Recent3month gap/breakout cannot reach20rounds; keep ineligible rather than relax the sample screen.
- Monthly selection must exclude candidates that halted in training stresses, even when terminal return is positive. Use carried AccountState for deployment and preserve full decision/account checkpoints; cash/halted months are legitimate zero-trade outcomes.
- Latest MICROSTRUCTURE_GRID_RETRY_REPORT_20261117.md: new64grid,2074engine calls,65tests,all rejected. Next measure development gap/volume complementarity before any capped exclusive combination; no blindly repeated grid or diagnostic-fit promotion.

2026-11-17 matched-event and routing-identifiability evidence:
- Separate fixed signal-cohort delayed-entry paths (same exit versus equal holding duration) from full account replay. Effects differed by half-year; do not call delayed account improvements universal timing alpha.
- Count distinct development entry arrays and actual interventions vs a source union.64 nominal routing configs produced8entry arrays/32signal-exit configs; most memory routers changed0-2bars only, so their mechanics were not identified. Preserve aliases and do not pad them with new thresholds.
- Use matched-exit pure components and non-summed source-union controls. Cached controls require data/engine/component/config hashes. Latest COHORT_ROUTING_RETRY_REPORT_20261117.md:1050newcalls,77tests,no approvals. Next fixed-union role attribution plus turnover-matched cash controls; close routing hypothesis if support is sparse or non-replicated, rather than re-sweep it.

2026-11-17 fixed-role falsification and closure:
- Distinguish exact-count/relative-weight conditional frozen-ledger cash matching (ex-post, not executable) from causal full-replay cash controls (expected participation only; realized turnover differs). Neither automatically matches dollar/time exposure or establishes causality.
- Freeze control seeds before outcomes; do not promote a profitable random seed. Report conditional-stratum support and active-session bootstrap limits. Current fixed daily-regime router failed six-cell information/futility checks and is CLOSED_FUTILITY; no more same-sample threshold tuning without new independent data/mechanism.
- Latest ROLE_INFORMATION_RETRY_REPORT_20261117.md:283newengine calls,64cash control repetitions (notalpha strategies),85tests. Next prioritize a separately versioned post-snapshot completed-bar data audit and frozen-model shadow monitoring; tiny new sample is not validation.


2026-11-18 interrupted-run recovery:
- A published RUNNING claim is not a completed report. Save compact aggregate checkpoints before lengthy follow-up reviews. Record prior terminal observations separately when unpublished outputs are lost. Never recreate a claimed exact CSV from rounded conversational metrics.
- Verify surviving input SHA and restore exact committed code in an isolated directory. Record fresh-data rate limits independently from successful archive replay. Do not call historical reproduction new strategy validation. Preserve expected-parent publication and record ownership evidence; do not infer remote-worker liveness from local process lists alone.


2026-11-18 signal provenance audit:
- For intraday event intent, check original event, transformed score and actual entry NY dates using logged signal_index and execution delay. A first-row reset alone does not enforce this. Preserve legacy semantics as a comparator; cross-session trading is a policy decision, not universally an error.
- Report preserved-ledger attribution separately from whole-account replay. If corrected provenance removes minimum sample eligibility, do not send the candidate into diagnostics. Archive actual finer-bar source/hashes and audit common complete sessions before new research.


2026-11-18 rank-gap evidence:
- Cross-ETF past-return rank gap is not an expected executable net edge. Report small-gap sample counts before inference; current <=4.6bp has only4events perhalf.
- Separate unchanged/filtered/ETF-switched baseline opportunities. Lower drawdown of one15% ETF versus two15% ETFs does not isolate information quality. Save compact completion summaries promptly so subsequent runners resume publication rather than repeat completed searches.


2026-11-18 true5min pilot:
- Form15min features only from three actual contiguous5min bars, releasing at the third bar end. An immediate nextopen assumes zero additional data latency; report5min delay separately from an hourly delay.
- Structurally complete sessions need all78expected starts per ETF. Keep short-window pilot conclusions and unavailable3/6month or2025 histories explicit. Current Yahoo2025five-minute query returned422 with last60days restriction. Do not relax min20 after seeing19rounds.


2026-11-18 same-event five-minute path audit:
- Require common same-session support across the longest latency plus equal-hold horizon. Same-exit cells whose exit precedes delayed entry are undefined and omitted as NA.
- Freeze original event/symbols for paired latency labels. Cluster descriptive differences by trading day because adjacent fifteen-minute events overlap. Price-path labels omit protection and cannot be reported as account returns; replay unchanged protected account separately.
- Nested threshold signals are not independent alpha sources. Count previously matched controls and new latency cells separately.


2026-11-18 event-episode evidence:
- Sparse15min scores on a5min timeline need explicit completed-decision neutral counters; zeros between decision clocks are unobserved decisions, not neutral confirmations.
- Freeze actual selected ETF anchor/range for retest and chase rules. Require an earlier observed bar to arm a retest before a later recovery, avoiding assumed OHLC path order.
- Report first/repeated-event paths by development window and full protected account replay separately. Current first/repeat advantage reverses; do not adopt onset-only based on one window. Keep minimum sample and short-history restrictions explicit.


2026-11-18 extended snapshot findings:
- Query common raw symbol/timestamp keys before common-session filters. Separate vintage/overlap changes, repaired session coverage and added earlier history. Current versus old1mo changed1027rows; current1mo andcurrent60d agree on oldkeys.
- Pin range/absolute-period parameters and actual returned dates. Current range60d returned60observed sessions, while prior absolute2025request said last60days; do not assume identical calendar semantics.
- Preserve reset-window result comparisons separately from one continuous account. Archive exact comparator regressions before interpreting altered performance as strategy improvement. Shorter one-ETF control exposure is not fully risk matched.


2026-11-18 structural-grid correction:
- Group candidates by effective development score-array hash before stress/diagnostic shortlist. Arm-only compression lifetime makes decompression invalidation redundant. Preserve preliminary results and cache-resume only missing unique cells when an alias is discovered after evaluation; record both nominal and unique counts.
- A source-code feature such as unexpired boxes or one-sided chase caps is a falsifiable concern, not evidence of loss causation. Reconstruct original event metadata and check its exact role-array agreement, then use development-only strata plus full account interventions.
- Flag overlapping roles/partial filters and changed event timing in frozen-parent attribution; do not turn baseline return sums into filtered portfolio returns.


2026-11-19 fixed-direction audit:
- Freeze direction-control seeds and stress IDs independently of PnL. Report control configurations separately from alpha trials; do not promote a profitable control seed.
- Preserve active roles and use actual bullish/inverse ETF paths at equal role budgets. Raw common-event labels test direction conditional on event timing; full replay does not match realized turnover/time/beta.
- Average random controls within each event before paired daily clustering; include zero-opportunity days. Show all four null families and multiday block sensitivity. Seed dispersion is not a market-sample confidence interval. Distinguish same-exit delayed labels from equal-holding evidence.


2026-11-19 external-reference pilot:
- Audit source-specific actual returned coverage before fitting; range60d may mean different calendar spans across ETF and24/7reference feeds. Exactjoin completedstarts/ends, keep frozenETFvintage, disclose unmatched source vintages and assumed publication latency.
- Count actual changed active roles on common opportunity support and full development arrays. New feeds almost duplicating ETF direction are not independent information sources; a20round account screen does not establish adequate intervention sample.
- Use return-blind event-count/warmup upper bounds before enlarging sparse-family grids. Keep minsample rejects and do not relax thresholds or add parameters to rescue a sparse winner. Preserve selection before diagnostics and publish compact aggregates before long narrative.


2026-11-19 source-lead identification and access audit:
- Preregister changed-role support, admitted/rejected counts and changed days before reading PnL. Account min20rounds does not establish a20intervention information sample.12sourcefilters and12matchedETF feature controls are not24independentalphas.
- Compare identical formulas/lags with only sourcefeed substituted, plus same-clock baseline and unrestricted baseline. Fixed-opportunity role labels and fullaccount replays answer different questions; count all failures even when support stops shortlist/stress/diagnosis.
- Keep ownership RUNNING while reports or acquisition audits continue after backtests; aggregate publication alone is not finalhandoff. Release COMPLETE only with checkpoint and next commands.
- Record newly acquired long history as ACCESS_ONLY until barcompletion, nulls, session clocks and vintages are audited. BTC hourly00 and ETF/QQQ mostly30minute starts cannot be called exact-clock bars or shifted/synthesized to match; completed sourcefeature age must be explicit. Newdownload is not an independentvalidation period.


2026-11-19 long hourly night-information evidence:
- Audit actualsourcebarend +declaredpublicationbuffer before ETFdecision. Do notshiftBTC00 bars intoETF30bars; logsourceage, trueRTHpullbackbarstarts, intentionalovernightanchorages andshortlastsessionbars. CurrentQQQopen mustnotdependonwholecurrentdaycompleteness. Preservepreliminarycontext andcorrectbeforePnL.
- Freeze globalcandidatepool on2025beforeany2026monthlyresearch. Recent3/6fits areonlythatpool andnotnext-monthreturns. Trainingstrictlyprecedingcalendar3/6months, allstresses/minrounds; continuousAccountState acrossflatmonthboundaries. Reportcashmonths,everhalt andcostfragility.
- Candidate min20account rounds differs fromnight-sourceintervention counts. NativeETFgap proxies canmakecapturethresholdmechanicallyredundant;preservecontrolaliases insteadofpaddinggrids. One15%role versuslegacytwo15%roles isnotriskmatched.
- Count completedresearch, additionalfrozenregression andabortedunpersistedcalls separately. Afterfirst/20calls saveaggregates. Ledger entry/end aretimestamps,signal_index isindex; verify their mapping. Exportboth start/end/callid foroverlappingtrainingwindows.
- Largepublicartifactreads mustbechunked andchecked against exactremotecontent/Gitblobhash. Terminaltruncation isnotavalidCSV; repairmetadatawithoutrepeatingbacktests. KeepownershipRUNNINGuntilfinalreport/handoffcomplete.


2026-11-19 fixed Nasdaq participation audit:
- Prove predicate-implied direction identities before calling source information. Current accepted BTC/QQQ sides are identical; source is a frozen session gate, not a separately identified directional forecast. Do not count identity aliases as new controls.
- Build all parent opportunities, including source-rejected days. Match only predeclared past-state strata; report overlap/eligible support before clustered uncertainty. Recent3 had no matched strata andrecent6only16admitted; do notloosen matching after outcomes to obtain significance.
- Fixed monthly-choice component replacement is not a causally retrained selector. Decompose dollar gross/cost contributions before interpreting fewer trades as source edge; entry delay can reverse relative price-path benefits.
- Resume the same owned RUNNING plan only after checking head/runid/surviving inputs/no active localworker/results/lock evidence; retain explicit external-worker limits. Save logs underpersistent run paths, notephemeral temporary paths.


2026-11-19 latency/holding decomposition:
- Record holding bars and actual wall-clock minutes separately. The final normal RTH bar is30min: four delayed bars need not equal240min. Before PnL, count common calendar support; zero equal-duration support is NOT_IDENTIFIED, not zero effect or a completed validation. Do not invent later exits/finer prices.
- Use identical frozen events/ETFs for paired path labels and preserve protection in full account replays. Same-exit, equal-bar and equal-minute contrasts answer different questions. In current source common cohort12/15<20, stop extra stress/diagnosis rather than relax the minimum.
- Track scheduled exit, actual protected exit price phase and reserved-slot release independently. End log timestamps are bar starts; equal-price open/close ambiguity must remain unresolved. Existing early_reentry=False reserves the original slot.
- Reuse a cached cell only after verifying immutable result/dependency blobs, exact inputs, config, reconstructed signals and execution definition. Count144new calls separately from8reused cells. Modified monthly state requires replay, never cached crypto splicing.
- A Nasdaq-only latency counterfactual is distinct from delaying every chosen policy. Fixed monthly choices are not a newly trained selector; current D recent improvement cannot override negative2025development. Keep actual data access limits, zero new independent validation and conditional unimplemented feed proposals explicit.


2026-11-19 actual5m release-clock evidence:
- Never backdate a complete hourly context row. Preserve only genuinely frozen preopen/prior-close fields and rejoin each actual dynamic source at its dependency end+assumed buffer. ETF first-hour completion/buffer must be explicit; adding it changes old assumptions.
- Apply coarse observation masks BEFORE onset state updates; off-clock rows are unobserved, not false confirmations. Pair by policy-used dependency snapshot/session/ETF, not calendar day alone or unused context fields.
- Require both account-round support and matched-intervention support in each development period. Current release5 parent180 had21/22rounds but14/17matched events; no stress/diagnosis. Exact180/240 prices now exist, but Nasdaq240 paired3/2 remains unidentified at required sample.
- Current+1bar stress means5min, not the previous60min. Keep protection frequency identical within clock contrasts; do not attribute old hourly-versus5m PnL differences to timing when vintage and first-hour buffers also changed.
- State MDD/peak/daily protection granularity: existing engine uses realized post-round equity, not continuous intrabar unrealized drawdown. Cooldown24finebars applies only under existing loss-streak logic and resets at the next day.
- JSON fractional return export at10decimals has up to5e-11 rounding error. Reconcile with currency PnL/explicit serialization bounds; preserve initial verifier failure, do not repeat completed backtests just to repair a verifier.


2026-11-19 source-activity grid evidence:
- Audit reported-volume quality before interpreting low values. CurrentBTC hourly is~50%zero and failed the prereg95%positive-per2025half gate; zero is unavailable here,not proof of low liquidity. QQQseasonal activity is a reported proxy,not actual flows.
- Normalize by all preceding20/40 normal calendar sessions in the same bar slot, requiring every donor positive/present; no currentday/future donor or skipping missing sessions. Match source/ETF feature actualstart/end+buffer and intersect support before onset.
- Fixed Bitcoin SIGNAL background does not fix realized Bitcoin trades/PnL under joint protection/slots/state. Keep whole-account replays and actual1/2role gross budgets; do not splice crypto results or call a30%cap portfolio riskmatched to a15%isolation audit.
- Require NasdaqactualBUY sample and source-vsETF interventions AND source-vs-volume-removed interventions separately. Pair controls occupy the bounded stress budget. Reject controls/aliases that look profitable only because Bitcoin trades supply all samples.
- Recentfull-window fit is not nextmonth performance. Train strictprior3/6months and require increment/nohigher realizedMDD versus the same fixedBitcoinbackground. Nasdaqcash fallback is not wholecash; distinguish explicitpolicycash from actualzero-trade months.
- Onset volume gates can create source-only event clocks. Publish source-only/control-only/same-target/switched partitions; fixed-cohort label averages are not whole-account returns. Volume-removed still retains volumeavailability support; a posthoc positive basic result is not a validated volume-independent strategy.
- Preserve round-trip float trade JSON. InfinitePF is a string in strict sharedJSON. For this immutable runner use source_activity_resume_guard: completed manifest/live lock/partial continuous prefix blocks automatic replay. Exact reset cache is reusable; missing carriedAccountState is a blocker, not permission to repeat prefixes.


2026-11-19 fixed-price availability ablation:
- A volume-removed policy may still require volume-history support. Separate price-only/current-positive/history20/history40 BEFORE onset, holding the price threshold/feed/clock/risk fixed. Audit volume-only-null raw rows before calling a signal history-volume-free.
- Identify literal support admission on a frozen none-event cohort separately from the actual gated onset stream and full portfolio. Current/L20 had0changed events in2025H1; no replicated availability-alpha claim. Source-only/control-only timing must remain explicit.
- Positive basic PnL is not fee or execution robustness. CurrentL20H1+.3115 became cost2-.7831 and delay-3.2387 withMDDhalt. Preserve cost/leg-dollar decomposition and actual trade-path equality; don't widen stops/leverage/horizon to rescue it.
- The plan's soft/hard wording exceeded direct instrumentation: engine records hard/MDDhalts, not softskipcounts. Derive postround daily soft-threshold contacts separately and label the limit; do not claim no soft halt without evidence.
- Persist intent BEFORE every engine call and commit ledger/results/FULLAccountState/schedule/planhash atomically BEFORE clearing intent. Before resume verify prefix ledgerSHA/call/month/fullstate/equitypeak. Unresolved intent or missing exact state is fail-closed.
- Keep an actual checkpoint-pause/resume proof, count existing prefix replay as0 only after hash/state reconciliation. Preserve original research-code hashes for storage-only guarded-launcher amendments. New strategy replays and recovery-regression calls are separate counts.
- Empty development pool means no new2026candidate fitting/diagnostic. Deterministic Nasdaqcash+fixedBitcoin fallback is not wholecash or new strategy validation. Cache exact reference windows; don't turn reused background returns into alpha.


2026-11-19 actual venue-flow evidence:
- Validate source schema/positive volume/duplicate/gap/taker quantity bounds and overlap vintage before PnL. Actual30m pairs may create1h:30 spans; never shift a00 source bar. Match actualETFspan plus declared source release buffer; disclose that clock gating itself removes firstdecision support.
- Reported taker-buy classification is not investor fund flow or consolidatedBTC. Hold sameBTCprice and common history support while removing ONLY flow predicates; derive control direction fromprice only. Count actualBitcoinBUY samples separately from fixedNasdaq background.
- Preserve price-control aliases and exact effective score-array counts before spending engine calls. Paired control metadata may share a single cached result; do not count these as independent trials. Next selector canonicalizes aliases before diagnostic metadata expansion.
- A recent3month allstresspositive fitted winner may remain useful for research while failing a strictprior3/6 nextmonth selector. Preserve the empty selections rather than loosen MDD/benchmark criteria after seeing them. Current22decisions allBitcoincash+priorNasdaq; do not call background profit newflowalpha.
- Decompose grossBitcoin/Nasdaq/cost contributions while recognizing jointslot/protection path changes. Frozenpricecontrol literalflow admission, actualsource onsets and fullaccount replay are different estimands. Here conditional block intervals included0 and noadoption.
- Latest VENUE_FLOW_RETRY_REPORT_20261119_1200.md:631unique calls,212testsPASS,48250ledger records verified,source/price partiallossreduction but alldevprofitscreensfailed. Actualpause/fullstate/hashprefixresume no duplicatefirstmonth. Sameflowgridclosed without newindependentdata/mechanism; rawpublicupload not retried.


2026-11-19 frozen Bitcoin-role isolation evidence:
- Full-account Bitcoinleg contribution is not Bitcoin-only replay. Role removal changes actualjointclose/protection/slots/entries/exits at15% vs30%gross; usefrozenfull labels AND actual15%account, nevercallthem riskmatched.
- Count BOTH pairedarms intervention support beforePnL. syncsource7~12events/half meansasync-removal information isalso sparseevenwhenasync standaloneevents>100. Preserveprice-only eligibilityasymmetry attemptbeforefix; do not useonlythehigher-supportarmtoqualifyapair.
- Forone-role research, compareflow to SAME15%priceandusepredeclaredabsoluteMDDscreen. RequiringMDD<=cash0mechanicallyrejectsnonflatpolicies; usingold30%backgroundMDDcanmisreadexposurereduction asalpha. Here3%selectionscreen didnotchangeengine5%kill.
- Twoanchors chosen partlyafterseeing2026recentwinnerremainretrospectiveevenifnew2025poolfrozenbeforefurther2026calls. Freezingpreventsadditionalleakagebutdoesnotrestoreindependence.
- Cache verifiesactualcost/delayvaluestogetherwithscenario andhashes/periods/exactexecutionarrays. Originalfull30cellswereverifiednotrerun. CurrentwholecashmonthlyfallbackisdistinctfrompriorBitcoinCash+Nasdaq;0return/0tradesisnotalphasuccessandwinrateNA.
- Latest VENUE_ISOLATION_RETRY_REPORT_20261119_1300.md:336newcalls+30priorunique,215testsPASS,26908new/3062priortraderows. Basic2025profitimprovedfromfull,butbothhalvesdelaynegative,reused2026negative,0adopted. Samefrozenisolationresweepclosed; nextfixed-event latency/holdingcommon-supportaudit oruntouchedshadow,notthresholdrescue.


2026-11-19 fixed-event calendar/holding evidence:
- Equalbarcounts are not equalactualminutes: on25/21events4barsmeanbase240/delay210min. Original4barrealminutesmaintainedafterdelayhas0commonsupport=>NOT_IDENTIFIED. NeverinventpostRTHprices. PlannedCLOSE andprotective nextOPEN mustbeexplicit,evenwhensameprice.
- hold1 joint_close has0intermediateprotectivechecks. Duration60labelsONLY,noprotectedaccounttrial;120/180retainhourlyprotectiveclockwith1/2observations. KeepcalendarcohortPITfromknownRTHschedule,notfuturequoteavailability.
- Calendarfiltersandholdingchangesneedfactorial controls: SAMEcohortH4c120/c180 vs h120/h180;unrestrictedH4cached. Identicalscorearrayswithdifferentholdarenotcachealiases;includeactualhold/cost/delay/exitsettings. MissingimmutablecachemustrejectBEFOREengine.
- Plannedexitinterventioncountdiffersfromactualprotectedchangedexitcount:180planned25/21butactual20/19. Keepmin20interventionrequirementevenwhen21accounttradesbarelypass. Frozenfilteredparentsums/pathmeansarenotaccountreturns.
- c180dev6profit/priceMDDscreenpassedwith25/21trades,butstrictprior6mnextmonth16tradeslost-.7854/-.8949/-.4692%;3mwholecash. Devscreenisnotadoption;16tradesand13recent3fitroundsdonotmeetminimum. Reused2026retrospective,nonewindependentvalidation.
- ClarifydeclaredWHOLECASHfallback vsactualcashmonthinmetadata;activeJan/Apr/Aug mustnotbelabeledcashbecausefallbackdefinitiontrue. Gateconcurrentread-onlyanalysisonresolvedintent;do notclearjournaltobypassguard.
- LatestVENUE_LATENCY_RETRY_REPORT_20261119_1400.md:669newcalls+30priorunique,221testsPASS,24428new/2711priorrows,66fullstatemonthsverified. Samegridclosed. Prospective2modelshadowplanfrozen2026-11-19 05:20:49 UTC withcode/risk/cost/hashes;noacquisitionyet,onlynewcompletedpostfreezeobservations,notautomaticindependent2026claim.
