import os
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

# Setup paths relative to the script location
BASE_DIR = Path(__file__).parent.resolve()
CSV_PATH = BASE_DIR / "trades.csv"
OUTPUT_XML_PATH = BASE_DIR / "Input" / "portfolio.xml"

# Make sure Input directory exists
os.makedirs(OUTPUT_XML_PATH.parent, exist_ok=True)

def prettify(elem):
    """Return a pretty-printed XML string for the Element."""
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    # Filter out empty/whitespace nodes to avoid double spacing
    return reparsed.toprettyxml(indent="  ")

def translate_csv_to_xml():
    # Read the client CSV file using pandas
    df = pd.read_csv(CSV_PATH)
    
    # Create the root Portfolio element
    portfolio = ET.Element("Portfolio")
    
    # Loop over each row in the CSV
    for _, row in df.iterrows():
        # Trade node
        trade_id = str(row['TradeID'])
        trade = ET.SubElement(portfolio, "Trade", id=trade_id)
        
        # TradeType
        trade_type = ET.SubElement(trade, "TradeType")
        trade_type.text = "EquityOption"
        
        # Envelope node
        envelope = ET.SubElement(trade, "Envelope")
        cpty = ET.SubElement(envelope, "CounterParty")
        cpty.text = str(row['Counterparty'])
        
        # NettingSetId and AdditionalFields (left empty but present)
        ET.SubElement(envelope, "NettingSetId")
        ET.SubElement(envelope, "AdditionalFields")
        
        # EquityOptionData node
        eq_opt_data = ET.SubElement(trade, "EquityOptionData")
        
        # OptionData
        option_data = ET.SubElement(eq_opt_data, "OptionData")
        
        long_short = ET.SubElement(option_data, "LongShort")
        long_short.text = str(row['LongShort'])
        
        option_type = ET.SubElement(option_data, "OptionType")
        option_type.text = str(row['OptionType'])
        
        style_mapping = {'E': 'European', 'A': 'American'}
        style_code = str(row.get('ExerciseStyle', 'E')).strip().upper()
        style_val = style_mapping.get(style_code, 'European')
        
        style = ET.SubElement(option_data, "Style")
        style.text = style_val
        
        exercise_dates = ET.SubElement(option_data, "ExerciseDates")
        ex_date = ET.SubElement(exercise_dates, "ExerciseDate")
        ex_date.text = str(row['ExpiryDate'])
        
        settlement = ET.SubElement(option_data, "Settlement")
        settlement.text = "Cash"
        
        # Premium Data (Optional)
        if pd.notna(row.get('PremiumAmount')) and pd.notna(row.get('PremiumCcy')) and pd.notna(row.get('PremiumDate')):
            amount = ET.SubElement(option_data, "PremiumAmount")
            amount.text = f"{float(row['PremiumAmount']):.2f}"
            
            ccy = ET.SubElement(option_data, "PremiumCurrency")
            ccy.text = str(row['PremiumCcy'])
            
            p_date = ET.SubElement(option_data, "PremiumPayDate")
            p_date.text = str(row['PremiumDate'])
            
        # Underlying
        underlying = ET.SubElement(eq_opt_data, "Underlying")
        u_type = ET.SubElement(underlying, "Type")
        u_type.text = "Equity"
        u_name = ET.SubElement(underlying, "Name")
        u_name.text = str(row['Underlying'])
        
        # Currency, Quantity, Strike
        currency = ET.SubElement(eq_opt_data, "Currency")
        currency.text = str(row['Currency'])
        
        quantity = ET.SubElement(eq_opt_data, "Quantity")
        quantity.text = f"{float(row['Quantity']):.2f}"
        
        strike = ET.SubElement(eq_opt_data, "Strike")
        strike.text = f"{float(row['Strike']):.2f}"
        
    # Pretty print the final XML representation
    xml_str = prettify(portfolio)
    
    # Save the output file
    with open(OUTPUT_XML_PATH, "w", encoding="utf-8") as f:
        # Avoid writing the duplicate xml declaration that minidom might add
        lines = xml_str.split("\n")
        if lines[0].startswith("<?xml"):
            lines = lines[1:]
        f.write("\n".join(lines))
        
    print(f"Successfully generated ORE Portfolio XML at: {OUTPUT_XML_PATH}")
    
    # Validate against local schema if available
    xsd_path = BASE_DIR / "xsd" / "input.xsd"
    if xsd_path.exists():
        validate_xml_with_local_xsd(OUTPUT_XML_PATH, xsd_path)
    else:
        print(f"\n[INFO] Local schema file not found at: {xsd_path}")
        print("Skipping local XML schema validation. Make sure the 'xsd/' folder is present.")

def validate_xml_with_local_xsd(xml_path, xsd_path):
    """Validate generated XML file against ORE's official input.xsd schema locally."""
    try:
        from lxml import etree
    except ImportError:
        print("\n[INFO] 'lxml' is not installed. Skipping XML schema validation.")
        print("To enable automatic schema validation, run: pip install lxml")
        return None

    print(f"\nValidating portfolio XML against ORE Schema ({xsd_path.name})...")
    try:
        # Load and parse the schema
        schema_doc = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(schema_doc)
        
        # Load and validate local XML
        xml_doc = etree.parse(str(xml_path))
        schema.assertValid(xml_doc)
        print("Success: Generated portfolio XML is valid against ORE schema.")
        return True
    except Exception as e:
        print(f"Validation Error: {e}")
        if isinstance(e, etree.DocumentInvalid):
            print("XML structure does not match ORE schema specifications:")
            for error in e.error_log:
                print(f"  Line {error.line}: {error.message}")
        return False

if __name__ == "__main__":
    translate_csv_to_xml()

