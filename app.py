import os
import io
import json
import base64
import datetime
import requests
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzLZTGDuPnEGpX3A8tc9uuaGXcmS1GQWsO2u75eXuU_ingUz1ipOLIPt9bVtaDZhoYitg/exec"
HISTORY_FILE = "checkin_history.json"

st.set_page_config(
    page_title="ระบบลงเวลาเข้า-ออกงาน | Smart Check-in",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (CSS)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Prompt', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .hero-header {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        padding: 24px 30px;
        border-radius: 16px;
        margin-bottom: 25px;
        box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.3);
    }
    .hero-header h1 {
        margin: 0;
        font-size: 1.9rem;
        font-weight: 700;
        color: white !important;
    }
    .hero-header p {
        margin: 8px 0 0 0;
        font-size: 0.95rem;
        opacity: 0.9;
    }
    
    .status-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    .success-box {
        background-color: #ECFDF5;
        border: 1px solid #10B981;
        border-radius: 12px;
        padding: 18px;
        margin-top: 15px;
    }
    
    .drive-link-btn {
        display: inline-block;
        background-color: #2563EB;
        color: white !important;
        padding: 8px 18px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 500;
        margin-top: 8px;
        transition: 0.2s;
    }
    .drive-link-btn:hover {
        background-color: #1D4ED8;
    }
    
    .tag-checkin {
        background-color: #DCFCE7;
        color: #15803D;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .tag-checkout {
        background-color: #FEE2E2;
        color: #B91C1C;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def load_history():
    """Load local history log."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(entry):
    """Save an entry to local history log."""
    history = load_history()
    history.insert(0, entry)  # latest first
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"บันทึกประวัติลงไฟล์ไม่สำเร็จ: {e}")

def get_system_font(size):
    """Locate a font supporting Thai/Unicode or fallback safely."""
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Thonburi.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/ThonburiUI.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def watermark_image(pil_img, emp_id, emp_name, date_str, time_str, check_type, location):
    """Stamp metadata watermark onto the image using PIL."""
    # Handle EXIF orientation
    img = ImageOps.exif_transpose(pil_img)
    
    # Scale down if overly large to optimize upload speed while keeping crispness
    max_dimension = 1280
    w, h = img.size
    if max(w, h) > max_dimension:
        if w > h:
            new_w = max_dimension
            new_h = int(h * (max_dimension / w))
        else:
            new_h = max_dimension
            new_w = int(w * (max_dimension / h))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        w, h = img.size

    # Prepare fonts based on image width
    base_size = max(16, int(w * 0.026))
    title_size = int(base_size * 1.25)
    
    font_title = get_system_font(title_size)
    font_body = get_system_font(base_size)

    # RGBA Overlay
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Calculate badge dimensions
    line_count = 4
    line_height = int(base_size * 1.35)
    card_h = int(line_height * line_count + base_size * 1.5)
    margin = max(16, int(w * 0.03))
    
    card_x0 = margin
    card_y0 = h - card_h - margin
    card_x1 = w - margin
    card_y1 = h - margin

    # Dark translucent background banner (Dark Slate with ~85% opacity)
    draw.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=14,
        fill=(15, 23, 42, 220)
    )

    # Accent color bar on the left
    is_checkin = "เข้างาน" in check_type or "Check-in" in check_type
    accent_color = (16, 185, 129, 255) if is_checkin else (239, 68, 68, 255)  # Green / Red
    draw.rounded_rectangle(
        [card_x0, card_y0, card_x0 + 10, card_y1],
        radius=4,
        fill=accent_color
    )

    # Watermark text lines
    pad_x = card_x0 + 24
    pad_y = card_y0 + int(base_size * 0.6)

    title_text = f"● {check_type.upper()}"
    title_color = (52, 211, 153, 255) if is_checkin else (248, 113, 113, 255)
    
    draw.text((pad_x, pad_y), title_text, fill=title_color, font=font_title)
    draw.text((pad_x, pad_y + line_height), f"👤 รหัส: {emp_id} | ชื่อ: {emp_name}", fill=(255, 255, 255, 255), font=font_body)
    draw.text((pad_x, pad_y + line_height * 2), f"📅 วันที่: {date_str}  เวลา: {time_str} น.", fill=(226, 232, 240, 255), font=font_body)
    draw.text((pad_x, pad_y + line_height * 3), f"📍 สถานที่: {location}", fill=(203, 213, 225, 255), font=font_body)

    # Composite & return RGB image
    watermarked = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return watermarked

def convert_to_base64(pil_image):
    """Convert PIL image to standard base64 string."""
    buffered = io.BytesIO()
    pil_image.save(buffered, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def send_checkin_webhook(date_str, time_str, emp_id, emp_name, check_type, location, base64_image, filename):
    """Send attendance data and base64 image to Google Apps Script webhook."""
    payload = {
        "date": date_str,
        "time": time_str,
        "datetime": f"{date_str} {time_str}",
        "id": emp_id,
        "employee_id": emp_id,
        "employeeId": emp_id,
        "name": emp_name,
        "employee_name": emp_name,
        "type": check_type,
        "action": check_type,
        "location": location,
        "filename": filename,
        "fileName": filename,
        "image_base64": base64_image,
        "image": base64_image
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=35)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"status": "success", "raw_response": response.text}
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "คำขอหมดเวลา (Request Timeout): Google Apps Script ใช้เวลาประมวลผลนานเกินกำหนด"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"การเชื่อมต่อล้มเหลว: {str(e)}"}

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.title("ระบบลงเวลางาน")
    st.caption("Google Drive & Sheets Integration")
    st.divider()

    st.subheader("⚙️ ข้อมูลผู้ใช้งานเบื้องต้น")
    default_emp_id = st.text_input("รหัสพนักงานประจำเครื่อง", value="EMP-001", help="จะถูกจำไว้ในเซสชันสำหรับการลงเวลาครั้งถัดไป")
    default_emp_name = st.text_input("ชื่อ-นามสกุล", value="สมชาย ใจดี")
    
    st.divider()
    st.markdown("### 🌐 สถานะระบบ")
    st.markdown("""
    - **Google Webhook:** 🟢 พร้อมใช้งาน
    - **Google Drive:** 📁 เชื่อมต่อแล้ว
    - **Google Sheets:** 📊 พร้อมบันทึก
    """)

    st.divider()
    now_live = datetime.datetime.now()
    st.info(f"🕒 เวลาปัจจุบัน:\n**{now_live.strftime('%d/%m/%Y %H:%M:%S')}**")

# ==========================================
# MAIN CONTENT & TABS
# ==========================================
st.markdown("""
<div class="hero-header">
    <h1>🕒 ระบบลงเวลาเข้า-ออกงาน (Smart Attendance System)</h1>
    <p>ระบบบันทึกเวลาทำงานพร้อมปั๊มลายน้ำบนรูปถ่าย อัปโหลดขึ้น Google Drive และบันทึกลง Google Sheets แบบเรียลไทม์</p>
</div>
""", unsafe_allow_html=True)

tab_checkin, tab_history, tab_guide = st.tabs([
    "📸 ลงเวลา (Check-in / Check-out)",
    "📜 ประวัติการลงเวลา (History)",
    "📖 คู่มือและคำแนะนำ (Guide)"
])

# ------------------------------------------
# TAB 1: CHECK-IN / CHECK-OUT
# ------------------------------------------
with tab_checkin:
    col_form, col_photo = st.columns([1, 1], gap="large")

    with col_form:
        st.subheader("1️⃣ ข้อมูลการลงเวลา")
        
        emp_id = st.text_input("รหัสพนักงาน (Employee ID)*", value=default_emp_id, placeholder="เช่น EMP-001")
        emp_name = st.text_input("ชื่อ-นามสกุล (Full Name)*", value=default_emp_name, placeholder="เช่น นายสมชาย ใจดี")

        check_type = st.radio(
            "ประเภทการลงเวลา (Action Type)*",
            options=["เข้างาน (Check-in)", "ออกงาน (Check-out)"],
            horizontal=True
        )

        location_preset = st.selectbox(
            "สถานที่ปฏิบัติงาน (Location)*",
            options=[
                "🏢 สำนักงานใหญ่ (Head Office)",
                "🏠 ทำงานที่บ้าน (Work From Home - WFH)",
                "🚗 ออกปฏิบัติงานนอกสถานที่ (Site / Client Visit)",
                "🏬 สาขา / คลังสินค้า (Branch / Warehouse)",
                "✍️ อื่นๆ (ระบุเอง)"
            ]
        )

        if "อื่นๆ" in location_preset:
            location_custom = st.text_input("ระบุสถานที่ปฏิบัติงาน", placeholder="เช่น หน่วยงาน กรมการขนส่งทางบก")
            location_final = location_custom if location_custom.strip() else "นอกสถานที่ (ไม่ได้ระบุ)"
        else:
            location_final = location_preset

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        st.caption(f"🗓️ บันทึก ณ วันที่: **{date_str}** | เวลา: **{time_str}**")

    with col_photo:
        st.subheader("2️⃣ ถ่ายรูปหรืออัปโหลดรูปภาพ")
        
        photo_mode = st.radio("เลือกวิธีแนบภาพถ่าย:", ["📷 ถ่ายภาพด้วยกล้อง (Camera)", "📁 อัปโหลดรูปภาพ (Upload File)"], horizontal=True)

        raw_image = None
        if photo_mode == "📷 ถ่ายภาพด้วยกล้อง (Camera)":
            camera_file = st.camera_input("กดถ่ายภาพใบหน้าหรือสถานที่ปฏิบัติงาน")
            if camera_file is not None:
                raw_image = Image.open(camera_file)
        else:
            uploaded_file = st.file_uploader("เลือกไฟล์รูปภาพจากเครื่อง", type=["png", "jpg", "jpeg", "webp"])
            if uploaded_file is not None:
                raw_image = Image.open(uploaded_file)

    st.divider()

    # WATERMARK PREVIEW & SUBMISSION
    if raw_image is not None:
        st.subheader("3️⃣ ตัวอย่างภาพถ่ายที่ปั๊มลายน้ำ (Watermarked Preview)")
        
        with st.spinner("กำลังปั๊มลายน้ำลงบนรูปภาพ..."):
            watermarked_img = watermark_image(
                pil_img=raw_image,
                emp_id=emp_id.strip() if emp_id else "N/A",
                emp_name=emp_name.strip() if emp_name else "N/A",
                date_str=date_str,
                time_str=time_str,
                check_type=check_type,
                location=location_final
            )

        col_preview, col_action = st.columns([1.2, 1], gap="medium")
        
        with col_preview:
            st.image(watermarked_img, caption="ตัวอย่างภาพที่จะส่งขึ้น Google Drive", use_container_width=True)

        with col_action:
            st.markdown("### 📋 สรุปข้อมูลที่จะส่งเข้าระบบ")
            badge_class = "tag-checkin" if "เข้างาน" in check_type else "tag-checkout"
            
            st.markdown(f"""
            - **ประเภท:** <span class="{badge_class}">{check_type}</span>
            - **รหัสพนักงาน:** `{emp_id}`
            - **ชื่อพนักงาน:** **{emp_name}**
            - **วันที่ & เวลา:** `{date_str} {time_str}`
            - **สถานที่:** {location_final}
            """, unsafe_allow_html=True)
            
            st.write("")
            submit_btn = st.button("🚀 ยืนยันและส่งข้อมูลลงเวลา (Submit)", type="primary", use_container_width=True)

            if submit_btn:
                if not emp_id.strip() or not emp_name.strip():
                    st.error("⚠️ กรุณาระบุรหัสพนักงานและชื่อ-นามสกุลให้ครบถ้วนก่อนบันทึก")
                else:
                    with st.spinner("⏳ กำลังแปลงรูปภาพเป็น Base64 และส่งข้อมูลไปยัง Google Apps Script Webhook..."):
                        # 1. Base64 encoding
                        b64_str = convert_to_base64(watermarked_img)
                        file_ext = "jpg"
                        action_tag = "IN" if "เข้างาน" in check_type else "OUT"
                        filename = f"{emp_id}_{action_tag}_{now.strftime('%Y%m%d_%H%M%S')}.{file_ext}"

                        # 2. HTTP POST to Webhook
                        res = send_checkin_webhook(
                            date_str=date_str,
                            time_str=time_str,
                            emp_id=emp_id.strip(),
                            emp_name=emp_name.strip(),
                            check_type=check_type,
                            location=location_final,
                            base64_image=b64_str,
                            filename=filename
                        )

                    # 3. Check Response
                    if res.get("status") == "success" or res.get("url"):
                        drive_url = res.get("url", "#")
                        st.balloons()
                        st.success("🎉 บันทึกข้อมูลและอัปโหลดรูปภาพขึ้น Google Drive สำเร็จเรียบร้อยแล้ว!")
                        
                        st.markdown(f"""
                        <div class="success-box">
                            <h4 style="color: #065F46; margin: 0 0 10px 0;">✅ ยืนยันการส่งข้อมูลสำเร็จ</h4>
                            <p style="margin: 0; color: #047857;">
                                ระบบได้บันทึกเวลา <b>{date_str} {time_str}</b> ลง Google Sheets และจัดเก็บภาพถ่ายหลักฐานใน Google Drive เรียบร้อยแล้ว
                            </p>
                            <br/>
                            <a href="{drive_url}" target="_blank" class="drive-link-btn">
                                📂 เปิดดูรูปภาพบน Google Drive
                            </a>
                        </div>
                        """, unsafe_allow_html=True)

                        # Save to history
                        new_record = {
                            "timestamp": f"{date_str} {time_str}",
                            "date": date_str,
                            "time": time_str,
                            "emp_id": emp_id.strip(),
                            "emp_name": emp_name.strip(),
                            "type": check_type,
                            "location": location_final,
                            "filename": filename,
                            "drive_url": drive_url
                        }
                        save_history(new_record)
                    else:
                        err_msg = res.get("message", "ไม่สามารถส่งข้อมูลได้ กรุณาลองใหม่อีกครั้ง")
                        st.error(f"❌ เกิดข้อผิดพลาดจากเซิร์ฟเวอร์: {err_msg}")
                        st.json(res)
    else:
        st.info("👆 กรุณาถ่ายภาพผ่านกล้อง หรืออัปโหลดภาพถ่ายเพื่อแสดงตัวอย่างการปั๊มลายน้ำและบันทึกเวลา")

# ------------------------------------------
# TAB 2: HISTORY
# ------------------------------------------
with tab_history:
    st.subheader("📜 ประวัติการลงเวลาล่าสุด (Attendance Logs)")
    
    history_data = load_history()

    if not history_data:
        st.info("ยังไม่มีประวัติการลงเวลาในระบบ ลองลงเวลาครั้งแรกที่แท็บ 'ลงเวลา (Check-in / Check-out)'")
    else:
        # Metrics row
        total_records = len(history_data)
        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        today_in = sum(1 for r in history_data if r.get("date") == today_date and "เข้างาน" in r.get("type", ""))
        today_out = sum(1 for r in history_data if r.get("date") == today_date and "ออกงาน" in r.get("type", ""))

        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("📊 รายการทั้งหมด", f"{total_records} รายการ")
        m_col2.metric("🟢 เข้างานวันนี้", f"{today_in} ครั้ง")
        m_col3.metric("🔴 ออกงานวันนี้", f"{today_out} ครั้ง")
        m_col4.metric("🕒 บันทึกล่าสุด", history_data[0].get("time", "-"))

        st.divider()

        # Search filter
        search_kw = st.text_input("🔍 ค้นหาตามชื่อ, รหัสพนักงาน หรือวันที่:", "")
        filtered_data = history_data
        if search_kw.strip():
            kw = search_kw.strip().lower()
            filtered_data = [
                r for r in history_data
                if kw in r.get("emp_id", "").lower()
                or kw in r.get("emp_name", "").lower()
                or kw in r.get("date", "").lower()
                or kw in r.get("location", "").lower()
            ]

        # Display table
        df_display = pd.DataFrame([
            {
                "วัน-เวลา": r.get("timestamp"),
                "รหัสพนักงาน": r.get("emp_id"),
                "ชื่อ-นามสกุล": r.get("emp_name"),
                "ประเภท": r.get("type"),
                "สถานที่": r.get("location"),
                "ชื่อไฟล์": r.get("filename"),
                "ลิงก์ Google Drive": r.get("drive_url")
            }
            for r in filtered_data
        ])

        st.dataframe(
            df_display,
            column_config={
                "ลิงก์ Google Drive": st.column_config.LinkColumn(
                    "ลิงก์ Google Drive",
                    display_text="📂 เปิดดูรูปภาพ"
                )
            },
            use_container_width=True,
            hide_index=True
        )

        # Download CSV
        csv_buffer = io.StringIO()
        df_display.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 ดาวน์โหลดประวัติเป็นไฟล์ CSV",
            data=csv_buffer.getvalue(),
            file_name=f"attendance_history_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# ------------------------------------------
# TAB 3: USER GUIDE & ARCHITECTURE
# ------------------------------------------
with tab_guide:
    st.subheader("📖 คำแนะนำและสถาปัตยกรรมการทำงานของระบบ")
    
    st.markdown("""
    ### 🔄 ขั้นตอนการทำงาน (System Workflow)
    1. **บันทึกข้อมูลพนักงาน:** ระบุรหัสพนักงาน ชื่อ ประเภทการลงเวลา (เข้างาน / ออกงาน) และสถานที่
    2. **ถ่ายรูป / แนบไฟล์:** ถ่ายภาพสดจากกล้องของอุปกรณ์ (โน้ตบุ๊ก หรือ สมาร์ตโฟน) หรืออัปโหลดไฟล์ภาพ
    3. **ปั๊มลายน้ำอัจฉริยะ (Pillow Watermarking):**
       - ระบบจะคำนวณตำแหน่งและปั๊มแถบข้อมูลลงบนรูปภาพ (ชื่อ, รหัส, วันที่, เวลา, ประเภท และสถานที่)
       - มีการปรับทิศทางภาพอัตโนมัติ (EXIF Orientation)
    4. **แปลงภาพเป็น Base64:** เข้ารหัสภาพถ่ายที่ปั๊มลายน้ำแล้วให้อยู่ในรูป Base64 String
    5. **ส่งผ่าน Webhook (HTTP POST):** ส่งข้อมูล JSON ไปยัง Google Apps Script Webhook URL
    6. **ประมวลผลบน Google Cloud:**
       - Google Apps Script จะถอดรหัส Base64 แล้วสร้างไฟล์ภาพบันทึกลงใน **Google Drive**
       - บันทึกแถวข้อมูล วัน, เวลา, รหัส, ชื่อ, สถานะ และแนบลิงก์รูปภาพลงใน **Google Sheets**
       - ส่ง URL ของไฟล์ใน Google Drive กลับมาให้ผู้ใช้งานตรวจสอบได้ทันที
    """)

    st.markdown("---")
    st.markdown("""
    ### 💡 เคล็ดลับการใช้งาน
    - **การขอสิทธิ์เข้าถึงกล้อง:** เมื่อกดใช้งานครั้งแรก เบราว์เซอร์จะถามการอนุญาตใช้งานกล้อง กรุณากด **Allow / อนุญาต**
    - **การใช้งานบนมือถือ:** สามารถเปิดผ่านเบราว์เซอร์บนสมาร์ตโฟน (Chrome / Safari) เพื่อสลับกล้องหน้า/กล้องหลังถ่ายภาพได้สะดวก
    - **ข้อมูลที่จำไว้:** รหัสและชื่อพนักงานในแถบด้านซ้าย (Sidebar) สามารถตั้งค่าไว้ล่วงหน้าเพื่อให้ไม่ต้องพิมพ์ใหม่ทุกครั้ง
    """)
