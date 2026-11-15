+++
# A Blank widget.
widget = "blank"  # See https://sourcethemes.com/academic/docs/page-builder/
headless = true  # This file represents a page section.
active = true  # Activate this widget? true/false
weight = 25  # Order that this section will appear.

title = "Expertise"
subtitle = "Quantitative Risk & Model Validation"

[design]
  # Choose how many columns the section has. Valid values: 1 or 2.
  columns = "2"

[design.background]
  # Apply a background color, gradient, or image.
+++

<div class="proto-lifecycle">
  <div class="proto-stage-card">
    <div class="proto-stage-body">
      <div class="proto-stage-kicker">Stage I · Calibration &amp; Pricing</div>
      <h3>Curves, Derivatives &amp; Market Data</h3>
      <div class="proto-stage-pair">
        <div class="proto-stage-sub"><strong>Derivative Pricing</strong><span>Multi-curve SOFR bootstrapping, swaps, caps, floors, swaptions, credit, and FX instruments.</span></div>
        <div class="proto-stage-sub"><strong>Open Source Risk Engine</strong><span>XML market configuration, Python trade adaptors, and C++ QuantLib parity checks.</span></div>
      </div>
    </div>
    <figure class="proto-stage-viz mb-0"><svg viewBox="0 0 160 66" aria-hidden="true"><line x1="8" y1="54" x2="152" y2="54" stroke="var(--p-hairline)" stroke-width="1"/><path d="M12 46 C 40 34, 72 22, 108 18 S 136 16, 148 14" fill="none" stroke="var(--p-accent)" stroke-width="2.2"/><circle cx="12" cy="46" r="2.8" fill="var(--p-card)" stroke="var(--p-accent)" stroke-width="1.8"/><circle cx="58" cy="27" r="2.8" fill="var(--p-card)" stroke="var(--p-accent)" stroke-width="1.8"/><circle cx="108" cy="18" r="2.8" fill="var(--p-card)" stroke="var(--p-accent)" stroke-width="1.8"/><circle cx="148" cy="14" r="2.8" fill="var(--p-card)" stroke="var(--p-accent)" stroke-width="1.8"/></svg><figcaption>Discount &amp; Fwd Spline</figcaption></figure>
  </div>
  <div class="proto-stage-card">
    <div class="proto-stage-body">
      <div class="proto-stage-kicker">Stage II · Exposure &amp; Valuation</div>
      <h3>Counterparty Credit &amp; XVA Engine</h3>
      <div class="proto-stage-pair">
        <div class="proto-stage-sub"><strong>XVA Modelling</strong><span>CVA, DVA, FVA, MVA, and KVA attribution alongside Jacobian par sensitivities.</span></div>
        <div class="proto-stage-sub"><strong>Counterparty Risk</strong><span>Monte Carlo PFE profiles, ISDA SIMM initial margin, and CSA netting mechanics.</span></div>
      </div>
    </div>
    <figure class="proto-stage-viz mb-0"><svg viewBox="0 0 160 66" aria-hidden="true"><line x1="8" y1="42" x2="152" y2="42" stroke="var(--p-hairline)" stroke-width="1"/><rect x="16" y="14" width="22" height="28" rx="2" fill="var(--p-accent)"/><rect x="46" y="42" width="22" height="14" rx="2" fill="var(--p-green)"/><rect x="76" y="22" width="22" height="20" rx="2" fill="var(--p-blue)"/><rect x="106" y="29" width="22" height="13" rx="2" fill="var(--p-ink-soft)"/><g fill="var(--p-ink-soft)" font-family="JetBrains Mono, monospace" font-size="7.5" text-anchor="middle"><text x="27" y="10">CVA</text><text x="57" y="64">DVA</text><text x="87" y="18">FVA</text><text x="117" y="25">KVA</text></g></svg><figcaption>XVA Bridge</figcaption></figure>
  </div>
  <div class="proto-stage-card">
    <div class="proto-stage-body">
      <div class="proto-stage-kicker">Stage III · Independent Challenge</div>
      <h3>Validation &amp; Supervisory Governance</h3>
      <div class="proto-stage-pair">
        <div class="proto-stage-sub"><strong>Model Validation</strong><span>Historical risk-factor backtesting, challenger prototypes, and stress testing.</span></div>
        <div class="proto-stage-sub"><strong>Regulatory Compliance</strong><span>Audit-ready documentation aligned with PRA SS1/23, FRTB, and Basel IV.</span></div>
      </div>
    </div>
    <figure class="proto-stage-viz mb-0"><svg viewBox="0 0 160 66" aria-hidden="true"><rect x="8" y="10" width="96" height="44" rx="3" fill="var(--p-green)" opacity="0.14"/><rect x="104" y="10" width="28" height="44" rx="3" fill="#f59e0b" opacity="0.18"/><rect x="132" y="10" width="20" height="44" rx="3" fill="var(--p-accent)" opacity="0.18"/><path d="M12 46 Q 48 16, 74 28 T 148 48" fill="none" stroke="var(--p-ink-strong)" stroke-width="1.8"/><line x1="104" y1="8" x2="104" y2="56" stroke="var(--p-accent)" stroke-width="1.2" stroke-dasharray="3 2"/></svg><figcaption>Traffic-Light Backtest</figcaption></figure>
  </div>
</div>
