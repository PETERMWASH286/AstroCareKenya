INSERT INTO laboratory_tests (test_name, department, sample_type, short_code, device_manufacturer, turnaround_time, is_active, loinc_code) VALUES
('AFB Examination (TB Test)', 'Microbiology', 'Sputum', 'AFB', NULL, '24:00:00', TRUE, NULL),
('LFTs', 'Biochemistry', 'Serum', 'LFT', NULL, '24:00:00', TRUE, NULL),
('Blood Group', 'Hematology', 'Blood (EDTA)', 'BG', NULL, '01:00:00', TRUE, NULL),
('Blood Sugar', 'Biochemistry', 'Plasma', 'BS', NULL, '01:00:00', TRUE, NULL),
('Blood Culture', 'Microbiology', 'Blood (EDTA)', 'BC', NULL, '48:00:00', TRUE, NULL),
('Bone Chemistry', 'Biochemistry', 'Serum', 'BC', NULL, '24:00:00', TRUE, NULL),
('Calcium Levels', 'Biochemistry', 'Serum', 'Ca', NULL, '24:00:00', TRUE, NULL),
('CK-MB Test', 'Biochemistry', 'Serum', 'CKMB', NULL, '24:00:00', TRUE, NULL),
('Coagulation Profile', 'Hematology', 'Plasma', 'CP', NULL, '24:00:00', TRUE, NULL),
('Covid Test', 'Serology', 'Nasopharyngeal Swab', 'COVID', NULL, '24:00:00', TRUE, NULL),
('CMG Test', 'Biochemistry', 'Serum', 'CMG', NULL, '24:00:00', TRUE, NULL),
('Crossmatch', 'Blood Bank', 'Blood (EDTA)', 'CM', NULL, '01:00:00', TRUE, NULL),
('CRP', 'Serology', 'Serum', 'CRP', NULL, '24:00:00', TRUE, NULL),
('CSF Test', 'Biochemistry', 'CSF', 'CSF', NULL, '24:00:00', TRUE, NULL),
('DCT Test', 'Hematology', 'Blood (EDTA)', 'DCT', NULL, '24:00:00', TRUE, NULL),
('D-Dimer', 'Hematology', 'Plasma', 'DDIMER', NULL, '24:00:00', TRUE, NULL),
('DU Test', 'Microbiology', 'Urine', 'DUT', NULL, '24:00:00', TRUE, NULL),
('Electrolytes', 'Biochemistry', 'Serum', 'ELEC', NULL, '01:00:00', TRUE, NULL),
('ESR', 'Hematology', 'Blood (EDTA)', 'ESR', NULL, '02:00:00', TRUE, NULL),
('Fasting Lipid Profile', 'Biochemistry', 'Serum', 'FLP', NULL, '24:00:00', TRUE, NULL),
('FBS', 'Biochemistry', 'Plasma', 'FBS', NULL, '01:00:00', TRUE, NULL),
('Full Haemogram', 'Hematology', 'Blood (EDTA)', 'FBC', NULL, '01:00:00', TRUE, NULL),
('Gram Stain', 'Microbiology', 'Various', 'GS', NULL, '24:00:00', TRUE, NULL),
('H. Pylori Test', 'Microbiology', 'Stool', 'HPYLORI', NULL, '24:00:00', TRUE, NULL),
('Hb Test', 'Hematology', 'Blood (EDTA)', 'HB', NULL, '01:00:00', TRUE, NULL),
('HbA1c', 'Biochemistry', 'Blood (EDTA)', 'HBA1C', NULL, '24:00:00', TRUE, NULL),
('Hepatitis A Ag', 'Serology', 'Serum', 'HEPAG', NULL, '24:00:00', TRUE, NULL),
('Hepatitis B Ab', 'Serology', 'Serum', 'HEPBB', NULL, '24:00:00', TRUE, NULL),
('Hepatitis C Ab', 'Serology', 'Serum', 'HEPC', NULL, '24:00:00', TRUE, NULL),
('HIV Test', 'Serology', 'Serum', 'HIV', NULL, '24:00:00', TRUE, NULL),
('INR', 'Hematology', 'Plasma', 'INR', NULL, '24:00:00', TRUE, NULL),
('ICT Test', 'Serology', 'Serum', 'ICT', NULL, '24:00:00', TRUE, NULL),
('Malaria Test', 'Microbiology', 'Blood (EDTA)', 'MALARIA', NULL, '01:00:00', TRUE, NULL),
('Micro Albumin', 'Biochemistry', 'Urine', 'MALB', NULL, '24:00:00', TRUE, NULL),
('Modified Zn Test', 'Biochemistry', 'Serum', 'MODZN', NULL, '24:00:00', TRUE, NULL),
('Occult Blood Test', 'Microbiology', 'Stool', 'OBT', NULL, '24:00:00', TRUE, NULL),
('OGTT', 'Biochemistry', 'Plasma', 'OGTT', NULL, '03:00:00', TRUE, NULL),
('Phosphate Levels', 'Biochemistry', 'Serum', 'PHOS', NULL, '24:00:00', TRUE, NULL),
('PITC', 'Microbiology', 'Various', 'PITC', NULL, '24:00:00', TRUE, NULL),
('Pregnancy Test (RPT)', 'Serology', 'Urine', 'RPT', NULL, '00:15:00', TRUE, NULL),
('PSA Test', 'Immunology', 'Serum', 'PSA', NULL, '24:00:00', TRUE, NULL),
('Pus Swab', 'Microbiology', 'Pus', 'PS', NULL, '48:00:00', TRUE, NULL),
('Rheumatoid Test (RF)', 'Serology', 'Serum', 'RF', NULL, '24:00:00', TRUE, NULL),
('Salmonella Test (SAT)', 'Serology', 'Serum', 'SAT', NULL, '24:00:00', TRUE, NULL),
('Stool O/C', 'Microbiology', 'Stool', 'SOC', NULL, '24:00:00', TRUE, NULL),
('TFTs', 'Endocrinology', 'Serum', 'TFT', NULL, '24:00:00', TRUE, NULL),
('UEC', 'Biochemistry', 'Serum', 'UEC', NULL, '01:00:00', TRUE, NULL),
('Urinalysis', 'Microbiology', 'Urine', 'UA', NULL, '01:00:00', TRUE, NULL),
('Uric Acid', 'Biochemistry', 'Serum', 'UA', NULL, '24:00:00', TRUE, NULL),
('VDRL', 'Serology', 'Serum', 'VDRL', NULL, '24:00:00', TRUE, NULL),
('Vitamin D Test', 'Immunology', 'Serum', 'VITD', NULL, '72:00:00', TRUE, NULL);


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Urea', NULL, 'mmol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Creatinine', NULL, 'umol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Bilirubin total', NULL, 'umol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Bilirubin direct', NULL, 'umol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Albumin IFCC', NULL, 'g/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Total Protein', NULL, 'g/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'ASAT/GOT', NULL, 'U/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'ALAT/GPT', NULL, 'U/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'gamma-GT', NULL, 'U/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'), 'Alk.Phos.DEA', NULL, 'U/L', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'AFB Examination (TB Test)'), 'AFB Result', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group'), 'ABO Group', NULL, NULL, 'categorical'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group'), 'Rh Factor', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Sugar'), 'Glucose Level', NULL, 'mmol/L', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Culture'), 'Culture Result', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Coagulation Profile'), 'Prothrombin Time (PT)', NULL, 'Sec', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Coagulation Profile'), 'Partial Thromboplastin Time (PTT)', NULL, 'Sec', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Coagulation Profile'), 'Activated Partial Thromboplastin Time (APTT)', NULL, 'Sec', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Coagulation Profile'), 'INR (International Normalized Ratio)', NULL, NULL, 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Covid Test'), 'COVID-19 Result', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Crossmatch'), 'Crossmatch Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'CRP'), 'C-Reactive Protein', NULL, 'mg/L', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'CSF Test'), 'CSF Protein', NULL, 'g/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'CSF Test'), 'CSF Glucose', NULL, 'mmol/L', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'DCT Test'), 'Direct Coombs Test', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'D-Dimer'), 'D-Dimer Level', NULL, 'ng/mL', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'DU Test'), 'Drug of Abuse Screen', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes'), 'Potassium (K)', NULL, 'mmol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes'), 'Sodium (Na)', NULL, 'mmol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes'), 'Chloride (Cl)', NULL, 'mmol/L', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'ESR'), 'Erythrocyte Sedimentation Rate', NULL, 'mm/hr', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'FBS'), 'Fasting Blood Sugar', NULL, 'mmol/L', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'WBC', NULL, '10^9/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'LYM', NULL, '10^9/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'MON', NULL, '10^9/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'GRA', NULL, '10^9/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'LYM%', NULL, '%', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'MON%', NULL, '%', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'GRA%', NULL, '%', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'RBC', NULL, '10^12/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'HGB', NULL, 'g/dl', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'HCT', NULL, '%', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'MCV', NULL, 'fl', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'MCH', NULL, 'pg', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'MCHC', NULL, 'g/dl', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'RDW%', NULL, '%', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'RDWc', NULL, NULL, 'numeric'), 

((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'PLT', NULL, '10^9/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'PCT', NULL, '%', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'MPV', NULL, 'fl', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'PDWs', NULL, NULL, 'numeric'), 
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'PDWc', NULL, NULL, 'numeric'), 
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'P-LCC', NULL, '10^9/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'), 'P-LCR', NULL, '%', 'numeric');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Gram Stain'), 'Gram Stain Result', NULL, NULL, 'text'); 

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'H. Pylori Test'), 'H. Pylori Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Hb Test'), 'Hemoglobin', NULL, 'g/dL', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'HbA1c'), 'HbA1c', NULL, '%', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis A Ag'), 'Hepatitis A Antigen Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis B Ab'), 'Hepatitis B Antibody Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis C Ab'), 'Hepatitis C Antibody Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'HIV Test'), 'HIV Test Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'INR'), 'INR Value', NULL, NULL, 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'ICT Test'), 'ICT Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Malaria Test'), 'Malaria Parasite', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Micro Albumin'), 'Microalbumin Level', NULL, 'mg/L', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Occult Blood Test'), 'Occult Blood Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'OGTT'), 'Glucose (0 min)', NULL, 'mmol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'OGTT'), 'Glucose (60 min)', NULL, 'mmol/L', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'OGTT'), 'Glucose (120 min)', NULL, 'mmol/L', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Phosphate Levels'), 'Phosphate', NULL, 'mmol/L', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'PITC'), 'PITC Test Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Pregnancy Test (RPT)'), 'Pregnancy Test Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'PSA Test'), 'PSA Level', NULL, 'Ng/ml', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Pus Swab'), 'Pus Swab Result', NULL, NULL, 'text'); 
INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Rheumatoid Test (RF)'), 'Rheumatoid Factor', NULL, NULL, 'categorical');


INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Salmonella Test (SAT)'), 'Salmonella Antibody', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Stool O/C'), 'Stool O&C Result', NULL, NULL, 'text'); 

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs'), 'T3', NULL, 'Nmol/l', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs'), 'T4', NULL, 'Nmol/l', 'numeric'),
((SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs'), 'TSH', NULL, 'Ulu/ml', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Urinalysis'), 'Urinalysis Result', NULL, NULL, 'text'); 

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Uric Acid'), 'Uric Acid Level', NULL, 'umol/L', 'numeric');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'VDRL'), 'VDRL Result', NULL, NULL, 'categorical');

INSERT INTO test_parameters (test_id, parameter_name, synonym, unit, result_type) VALUES
((SELECT test_id FROM laboratory_tests WHERE test_name = 'Vitamin D Test'), 'Vitamin D Level', NULL, 'ng/mL', 'numeric');

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'T3' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 0, 120, 'Years', 'Any', 1.23, 3.08, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'T3' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 1, 10, 'Years', 'Any', 1.26, 4.34, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'T4' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 0, 120, 'Years', 'Any', 57.9, 150.6, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'TSH' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 20, 54, 'Years', 'Any', 0.4, 4.2, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'TSH' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 55, 87, 'Years', 'Any', 0.5, 8.9, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'TSH' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 0, 1, 'Years', 'Any', 0.4, 8.6, NULL, NULL), -- 1yr
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'TSH' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs')), 4, 19, 'Years', 'Any', 0.4, 6.2, NULL, NULL); -- 4-19yr

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'PSA Level' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'PSA Test')), 0, 120, 'Years', 'Any', NULL, 4.0, NULL, NULL); -- Below 4.0

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HbA1c' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'HbA1c')), 0, 120, 'Years', 'Any', 4.5, 6.5, NULL, NULL);


INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Cholesterol' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Fasting Lipid Profile')), 0, 120, 'Years', 'Any', NULL, 5.18, NULL, NULL);

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HDL' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Fasting Lipid Profile')), 0, 120, 'Years', 'Any', 1.6, NULL, NULL, NULL); 

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Triglycerides' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Fasting Lipid Profile')), 0, 120, 'Years', 'Any', NULL, 1.7, NULL, NULL); 

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'LDL' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Fasting Lipid Profile')), 0, 120, 'Years', 'Any', NULL, 3.35, NULL, NULL);

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Prothrombin Time (PT)' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Coagulation Profile')), 0, 120, 'Years', 'Any', 11.0, 14.0, NULL, NULL);

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Potassium (K)' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes')), 0, 120, 'Years', 'Any', 3.5, 5.5, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Sodium (Na)' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes')), 0, 120, 'Years', 'Any', 135.0, 145.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Chloride (Cl)' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes')), 0, 120, 'Years', 'Any', 98.0, 108.0, NULL, NULL);

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Urea' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 1.7, 8.3, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Creatinine' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 53.0, 97.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Bilirubin total' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 2.0, 21.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Bilirubin direct' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 0.0, 3.42, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Albumin IFCC' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 38.0, 51.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Total Protein' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 66.0, 87.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ASAT/GOT' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 0.0, 35.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ALAT/GPT' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 0.0, 42.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'gamma-GT' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 11.0, 61.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Alk.Phos.DEA' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs')), 0, 120, 'Years', 'Any', 80.0, 306.0, NULL, NULL);

INSERT INTO parameter_ranges (parameter_id, age_min, age_max, age_unit, sex, normal_min, normal_max, critical_min, critical_max) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'WBC' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 4.0, 11.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'LYM' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 1.30, 4.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'MON' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 0.15, 0.70, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'GRA' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 2.00, 7.50, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'LYM%' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 25.0, 40.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'MON%' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 3.0, 7.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'GRA%' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 50.0, 75.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'RBC' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 4.0, 6.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HGB' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 12.0, 16.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HCT' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 36.0, 48.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'MCV' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 76.0, 96.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'MCH' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 27.0, 32.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'MCHC' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 30.0, 35.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'RDW%' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 11.5, 14.5, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'PLT' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 150.0, 450.0, NULL, NULL),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'MPV' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram')), 0, 120, 'Years', 'Any', 8.0, 15.0, NULL, NULL);


INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'AFB Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'AFB Examination (TB Test)')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'AFB Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'AFB Examination (TB Test)')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ABO Group' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group')), 'A', 'A'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ABO Group' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group')), 'B', 'B'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ABO Group' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group')), 'AB', 'AB'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ABO Group' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group')), 'O', 'O');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Rh Factor' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group')), 'Positive', 'POS'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Rh Factor' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Group')), 'Negative', 'NEG');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Culture Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Culture')), 'No Growth', 'NG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Culture Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Blood Culture')), 'Growth (Specify Organism)', 'GR');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'COVID-19 Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Covid Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'COVID-19 Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Covid Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Crossmatch Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Crossmatch')), 'Compatible', 'COMP'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Crossmatch Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Crossmatch')), 'Incompatible', 'INCOMP');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Direct Coombs Test' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'DCT Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Direct Coombs Test' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'DCT Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Drug of Abuse Screen' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'DU Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Drug of Abuse Screen' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'DU Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'H. Pylori Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'H. Pylori Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'H. Pylori Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'H. Pylori Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Hepatitis A Antigen Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis A Ag')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Hepatitis A Antigen Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis A Ag')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Hepatitis B Antibody Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis B Ab')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Hepatitis B Antibody Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis B Ab')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Hepatitis C Antibody Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis C Ab')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Hepatitis C Antibody Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Hepatitis C Ab')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HIV Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'HIV Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HIV Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'HIV Test')), 'Positive', 'POS'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'HIV Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'HIV Test')), 'Indeterminate', 'IND');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ICT Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'ICT Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'ICT Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'ICT Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Malaria Parasite' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Malaria Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Malaria Parasite' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Malaria Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Occult Blood Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Occult Blood Test')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Occult Blood Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Occult Blood Test')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'PITC Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'PITC')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'PITC Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'PITC')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Pregnancy Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Pregnancy Test (RPT)')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Pregnancy Test Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Pregnancy Test (RPT)')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Rheumatoid Factor' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Rheumatoid Test (RF)')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Rheumatoid Factor' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Rheumatoid Test (RF)')), 'Positive', 'POS');

INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Salmonella Antibody' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Salmonella Test (SAT)')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'Salmonella Antibody' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'Salmonella Test (SAT)')), 'Positive', 'POS');


INSERT INTO parameter_options (parameter_id, option_value, option_code) VALUES
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'VDRL Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'VDRL')), 'Negative', 'NEG'),
((SELECT parameter_id FROM test_parameters WHERE parameter_name = 'VDRL Result' AND test_id = (SELECT test_id FROM laboratory_tests WHERE test_name = 'VDRL')), 'Positive', 'POS');


INSERT INTO test_panels (panel_name, is_active) VALUES
('Thyroid Function Test', TRUE),
('Lipid Profile', TRUE),
('Electrolyte Panel', TRUE),
('Complete Blood Count (CBC)', TRUE),
('Liver Function Test', TRUE);




INSERT INTO panel_tests (panel_id, test_id) VALUES
((SELECT panel_id FROM test_panels WHERE panel_name = 'Thyroid Function Test'), (SELECT test_id FROM laboratory_tests WHERE test_name = 'TFTs'));

INSERT INTO panel_tests (panel_id, test_id) VALUES
((SELECT panel_id FROM test_panels WHERE panel_name = 'Lipid Profile'), (SELECT test_id FROM laboratory_tests WHERE test_name = 'Fasting Lipid Profile'));

INSERT INTO panel_tests (panel_id, test_id) VALUES
((SELECT panel_id FROM test_panels WHERE panel_name = 'Electrolyte Panel'), (SELECT test_id FROM laboratory_tests WHERE test_name = 'Electrolytes'));

INSERT INTO panel_tests (panel_id, test_id) VALUES
((SELECT panel_id FROM test_panels WHERE panel_name = 'Complete Blood Count (CBC)'), (SELECT test_id FROM laboratory_tests WHERE test_name = 'Full Haemogram'));

INSERT INTO panel_tests (panel_id, test_id) VALUES
((SELECT panel_id FROM test_panels WHERE panel_name = 'Liver Function Test'), (SELECT test_id FROM laboratory_tests WHERE test_name = 'LFTs'));