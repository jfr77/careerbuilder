# Roadmap (explicitly out of scope for the MVP)

## Employer-side candidate ranking
Features that rank or score candidates *for employers* (candidate leaderboards,
"top X% candidate" badges, employer dashboards) are deliberately not built.
Under the EU AI Act, AI systems used for recruitment-side evaluation of natural
persons fall into the high-risk category (Annex III), which triggers conformity
assessment, logging, human-oversight and transparency obligations. If this is
ever pursued, it needs a dedicated compliance work stream first; until then the
product stays strictly candidate-side: people score *jobs for themselves*, not
the other way around.

## Onboarding workflow / HRIS integration
A future version could hand a successful application off into the employer's
HR stack (e.g. Personio, Workday, SAP SuccessFactors): pushing the accepted
candidate's data into onboarding, contract generation, and IT provisioning
flows. That requires per-vendor API integrations, consent and data-minimization
design (the pipeline holds more personal context than an employer should
receive), and webhook infrastructure for status sync — none of which belongs in
a local-first personal tool yet. Tracked here so the data model keeps a clean
boundary: everything an employer would receive lives in `pipeline` + generated
documents, never the raw profile.
