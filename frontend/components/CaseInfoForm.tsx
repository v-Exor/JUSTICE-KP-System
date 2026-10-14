import { useState } from "react";

import type { CaseInformation } from "./CaseAnalysis";

type Option = {
  label: string;
  value: string;
};

const caseTypes: Option[] = [
  { label: "Civil", value: "civil" },
  { label: "Criminal", value: "criminal" },
  { label: "Administrative", value: "administrative" },
  { label: "Other", value: "other" },
];

const disputeCategories: Option[] = [
  { label: "Debt", value: "debt" },
  { label: "Boundary", value: "boundary" },
  { label: "Family Dispute", value: "family_dispute" },
  { label: "Physical Injury", value: "physical_injury" },
  { label: "Nuisance", value: "nuisance" },
  { label: "Threat", value: "threat" },
  { label: "Property Damage", value: "property_damage" },
  { label: "Online Defamation (Cyber Libel)", value: "online_defamation" },
  { label: "Neighbor Altercation", value: "neighbor_altercation" },
  { label: "Harassment / Unjust Vexation", value: "harassment_unjust_vexation" },
  { label: "Business Defamation (Slander)", value: "business_defamation" },
  { label: "Other", value: "other" },
];

type NumericCaseField = "debt_amount_php" | "maximum_penalty_years" | "fine_amount_php";
type NumericFieldApplicability = Record<NumericCaseField, boolean>;

const noNumericFields: NumericFieldApplicability = {
  debt_amount_php: false,
  maximum_penalty_years: false,
  fine_amount_php: false,
};

const disputeNumericFields: Record<Exclude<CaseInformation["dispute_category"], "">, NumericFieldApplicability> = {
  debt: { debt_amount_php: true, maximum_penalty_years: false, fine_amount_php: false },
  boundary: { ...noNumericFields },
  family_dispute: { ...noNumericFields },
  physical_injury: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  nuisance: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  threat: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  property_damage: { debt_amount_php: true, maximum_penalty_years: true, fine_amount_php: true },
  online_defamation: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  neighbor_altercation: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  harassment_unjust_vexation: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  business_defamation: { debt_amount_php: false, maximum_penalty_years: true, fine_amount_php: true },
  other: { debt_amount_php: true, maximum_penalty_years: true, fine_amount_php: true },
};

export function applicableNumericFields(
  category: CaseInformation["dispute_category"],
): NumericFieldApplicability {
  return category ? disputeNumericFields[category] : noNumericFields;
}

const residencyOptions: Option[] = [
  { label: "Same Barangay", value: "same_barangay" },
  { label: "Adjacent Barangay", value: "adjacent_barangay" },
  { label: "Different Municipality", value: "different_municipality" },
];

function inputClassName() {
  return "mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-950 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100";
}

function inputValue(value: string | number | null | undefined) {
  return value ?? "";
}

type NumericFieldMode = "value" | "to_be_discussed";

function initialNumericFieldMode(value: number | "" | null | undefined): NumericFieldMode {
  return value === "" || value === null || value === undefined ? "to_be_discussed" : "value";
}

export default function CaseInfoForm({
  value,
  onChange,
}: {
  value: CaseInformation;
  onChange: (value: CaseInformation) => void;
}) {
  // Keep the user's selected mode separate from the input value. An empty string
  // is a valid temporary editing state and must not switch the dropdown.
  const [numericFieldModes, setNumericFieldModes] = useState<Record<NumericCaseField, NumericFieldMode>>(() => ({
    debt_amount_php: initialNumericFieldMode(value.debt_amount_php),
    maximum_penalty_years: initialNumericFieldMode(value.maximum_penalty_years),
    fine_amount_php: initialNumericFieldMode(value.fine_amount_php),
  }));

  const set = <K extends keyof CaseInformation>(key: K, nextValue: CaseInformation[K]) => {
    onChange({ ...value, [key]: nextValue });
  };
  const setNumericField = (key: NumericCaseField, nextValue: number | "" | null) => {
    onChange({ ...value, [key]: nextValue });
  };
  const setDisputeCategory = (category: CaseInformation["dispute_category"]) => {
    if (category === value.dispute_category) {
      return;
    }
    setNumericFieldModes({
      debt_amount_php: "to_be_discussed",
      maximum_penalty_years: "to_be_discussed",
      fine_amount_php: "to_be_discussed",
    });
    onChange({
      ...value,
      dispute_category: category,
      debt_amount_php: null,
      maximum_penalty_years: null,
      fine_amount_php: null,
    });
  };
  const numericField = (
    key: NumericCaseField,
    label: string,
    options: { min?: number; step?: string } = {},
  ) => {
    const mode = numericFieldModes[key];

    return (
      <label className="block text-sm font-bold text-gray-700">
        {label}
        <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <select
            className="h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-950 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
            onChange={(event) => {
              const nextMode = event.target.value as NumericFieldMode;
              setNumericFieldModes((current) => ({ ...current, [key]: nextMode }));
              setNumericField(key, nextMode === "to_be_discussed" ? null : 0);
            }}
            value={mode}
          >
            <option value="value">Enter value</option>
            <option value="to_be_discussed">To be discussed</option>
          </select>
          {mode === "value" ? (
            <input
              className="h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-950 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
              min={options.min ?? 0}
              onChange={(event) => setNumericField(key, event.target.value ? Number(event.target.value) : "")}
              step={options.step}
              type="number"
              value={inputValue(value[key])}
            />
          ) : (
            <span className="flex h-10 items-center rounded-md border border-dashed border-gray-300 bg-gray-50 px-3 text-sm font-bold text-gray-500">
              To be discussed
            </span>
          )}
        </div>
      </label>
    );
  };

  const applicableFields = applicableNumericFields(value.dispute_category);

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5">
      <h3 className="font-black text-gray-950">Case Information Form</h3>
      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <label className="block text-sm font-bold text-gray-700">
          Case ID
          <input className={inputClassName()} onChange={(event) => set("case_id", event.target.value)} value={inputValue(value.case_id)} />
        </label>
        <label className="block text-sm font-bold text-gray-700">
          Barangay Name
          <input className={inputClassName()} onChange={(event) => set("barangay_name", event.target.value)} value={inputValue(value.barangay_name)} />
        </label>
        <label className="block text-sm font-bold text-gray-700">
          City/Municipality
          <input className={inputClassName()} onChange={(event) => set("city_municipality", event.target.value)} value={inputValue(value.city_municipality)} />
        </label>
        <label className="block text-sm font-bold text-gray-700">
          Case Year
          <input className={inputClassName()} min={1900} onChange={(event) => set("case_year", event.target.value ? Number(event.target.value) : "")} type="number" value={inputValue(value.case_year)} />
        </label>
        <label className="block text-sm font-bold text-gray-700">
          Case Type
          <select className={inputClassName()} onChange={(event) => set("case_type", event.target.value as CaseInformation["case_type"])} value={inputValue(value.case_type)}>
            {caseTypes.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="block text-sm font-bold text-gray-700">
          Dispute Category
          <select className={inputClassName()} onChange={(event) => setDisputeCategory(event.target.value as CaseInformation["dispute_category"])} required value={inputValue(value.dispute_category)}>
            <option disabled value="">Select dispute category</option>
            {disputeCategories.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="block text-sm font-bold text-gray-700">
          Complainant Residency
          <select className={inputClassName()} onChange={(event) => set("complainant_residency", event.target.value as CaseInformation["complainant_residency"])} value={inputValue(value.complainant_residency)}>
            {residencyOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="block text-sm font-bold text-gray-700">
          Respondent Residency
          <select className={inputClassName()} onChange={(event) => set("respondent_residency", event.target.value as CaseInformation["respondent_residency"])} value={inputValue(value.respondent_residency)}>
            {residencyOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        {applicableFields.debt_amount_php && numericField(
          "debt_amount_php",
          value.dispute_category === "property_damage" ? "Property Damage Amount PHP" : "Debt Amount PHP",
        )}
        {applicableFields.maximum_penalty_years && numericField("maximum_penalty_years", "Maximum Penalty Years", { step: "0.1" })}
        {applicableFields.fine_amount_php && numericField("fine_amount_php", "Fine Amount PHP")}
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <label className="flex items-center gap-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm font-bold text-gray-800">
          <input checked={Boolean(value.government_party_involved)} className="size-4 accent-blue-600" onChange={(event) => set("government_party_involved", event.target.checked)} type="checkbox" />
          Government Party Involved
        </label>
        <label className="flex items-center gap-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm font-bold text-gray-800">
          <input checked={Boolean(value.already_filed_in_court)} className="size-4 accent-blue-600" onChange={(event) => set("already_filed_in_court", event.target.checked)} type="checkbox" />
          Already Filed In Court
        </label>
        <label className="flex items-center gap-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm font-bold text-gray-800">
          <input checked={Boolean(value.has_vawc_or_child_abuse_indicators)} className="size-4 accent-red-600" onChange={(event) => set("has_vawc_or_child_abuse_indicators", event.target.checked)} type="checkbox" />
          Has VAWC or Child Abuse Indicators
        </label>
      </div>
    </section>
  );
}
