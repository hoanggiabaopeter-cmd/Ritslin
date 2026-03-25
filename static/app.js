const state = {
  token: localStorage.getItem("mvp_token") || "",
  user: JSON.parse(localStorage.getItem("mvp_user") || "null"),
  scanner: null,
  scanning: false,
  classes: [],
  students: [],
};

const authInfo = document.getElementById("authInfo");
const scanMessage = document.getElementById("scanMessage");
const statsBox = document.getElementById("statsBox");
const classList = document.getElementById("classList");
const studentList = document.getElementById("studentList");
const attendanceList = document.getElementById("attendanceList");

const studentClassSelect = document.getElementById("studentClassSelect");
const attendanceClassSelect = document.getElementById("attendanceClassSelect");

function showMessage(message, type = "success") {
  scanMessage.className = `message ${type}`;
  scanMessage.textContent = message;
}

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function getJSON(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Yêu cầu thất bại");
  return data;
}

function updateAuthInfo() {
  if (state.user) {
    authInfo.textContent = `Đăng nhập: ${state.user.username} (${state.user.role})`;
  } else {
    authInfo.textContent = "Chưa đăng nhập";
  }
}

function renderClassOptions() {
  const optionsHtml =
    '<option value="">-- Chọn lớp --</option>' +
    state.classes.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  studentClassSelect.innerHTML = optionsHtml;
  attendanceClassSelect.innerHTML = optionsHtml;
}

function renderClasses() {
  classList.innerHTML = "";
  if (!state.classes.length) {
    classList.innerHTML = "<li>Chưa có lớp.</li>";
    return;
  }

  state.classes.forEach((c) => {
    const li = document.createElement("li");
    li.className = "item";
    li.innerHTML = `<strong>${c.name}</strong> <button class="danger small">Xóa</button>`;
    li.querySelector("button").addEventListener("click", async () => {
      try {
        await getJSON(`/api/classes/${c.id}`, { method: "DELETE" });
        showMessage(`Đã xóa lớp ${c.name}`);
        await refreshAll();
      } catch (err) {
        showMessage(err.message, "error");
      }
    });
    classList.append(li);
  });
}

function renderStudents() {
  studentList.innerHTML = "";
  if (!state.students.length) {
    studentList.innerHTML = "<li>Chưa có học sinh.</li>";
    return;
  }

  state.students.forEach((s) => {
    const li = document.createElement("li");
    li.className = "item";
    const avatar = s.avatar_base64 ? `<img class="avatar" src="data:image/png;base64,${s.avatar_base64}" alt="avatar" />` : "";
    li.innerHTML = `
      <div>
        ${avatar}
        <strong>${s.full_name}</strong> (${s.id}) - Lớp: ${s.class_name || "Chưa gán"}<br>
        PH: ${s.parent_name || "-"} | SĐT: ${s.parent_phone || "-"}
      </div>
      <div class="student-actions">
        <img class="qr" src="/api/students/${encodeURIComponent(s.id)}/qrcode" alt="QR ${s.id}" />
        <button class="danger small">Xóa</button>
      </div>
    `;

    li.querySelector("button").addEventListener("click", async () => {
      try {
        await getJSON(`/api/students/${encodeURIComponent(s.id)}`, { method: "DELETE" });
        showMessage(`Đã xóa học sinh ${s.id}`);
        await refreshAll();
      } catch (err) {
        showMessage(err.message, "error");
      }
    });

    studentList.append(li);
  });
}

function renderAttendance(logs) {
  attendanceList.innerHTML = "";
  if (!logs.length) {
    attendanceList.innerHTML = "<li>Chưa có điểm danh.</li>";
    return;
  }

  logs.forEach((log) => {
    const li = document.createElement("li");
    li.className = "item";
    li.innerHTML = `${log.student_name} (${log.student_id}) - ${log.class_name} - ${log.attendance_date}`;
    attendanceList.append(li);
  });
}

function renderStats(stats) {
  statsBox.innerHTML = `
    <strong>Tổng:</strong> ${stats.total} |
    <strong>Có mặt:</strong> ${stats.present} |
    <strong>Vắng:</strong> ${stats.absent} |
    <strong>Tỷ lệ:</strong> ${stats.rate}%
  `;
}

async function loadClasses() {
  state.classes = await getJSON("/api/classes");
  renderClassOptions();
  renderClasses();
}

async function loadStudents() {
  state.students = await getJSON("/api/students");
  renderStudents();
}

async function loadAttendanceAndStats() {
  const classId = attendanceClassSelect.value;
  if (!classId) {
    renderAttendance([]);
    statsBox.textContent = "Chọn lớp để xem thống kê.";
    return;
  }

  const [logs, stats] = await Promise.all([
    getJSON(`/api/attendance?class_id=${classId}&attendance_date=${new Date().toISOString().slice(0, 10)}`),
    getJSON(`/api/attendance/stats?class_id=${classId}&attendance_date=${new Date().toISOString().slice(0, 10)}`),
  ]);

  renderAttendance(logs);
  renderStats(stats);
}

async function refreshAll() {
  if (!state.token) return;
  await loadClasses();
  await loadStudents();
  await loadAttendanceAndStats();
}

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await getJSON("/api/auth/login", {
      method: "POST",
      headers: {},
      body: JSON.stringify({
        username: document.getElementById("loginUsername").value.trim(),
        password: document.getElementById("loginPassword").value,
      }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("mvp_token", state.token);
    localStorage.setItem("mvp_user", JSON.stringify(state.user));
    updateAuthInfo();
    showMessage("Đăng nhập thành công.");
    await refreshAll();
  } catch (err) {
    showMessage(err.message, "error");
  }
});

document.getElementById("createUserForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await getJSON("/api/users", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("newUsername").value.trim(),
        password: document.getElementById("newPassword").value,
        role: document.getElementById("newRole").value,
      }),
    });
    showMessage("Tạo user thành công.");
    event.target.reset();
  } catch (err) {
    showMessage(err.message, "error");
  }
});

document.getElementById("classForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await getJSON("/api/classes", {
      method: "POST",
      body: JSON.stringify({ name: document.getElementById("classNameInput").value.trim() }),
    });
    event.target.reset();
    await refreshAll();
    showMessage("Tạo lớp thành công.");
  } catch (err) {
    showMessage(err.message, "error");
  }
});

document.getElementById("studentForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await getJSON("/api/students", {
      method: "POST",
      body: JSON.stringify({
        id: document.getElementById("studentId").value.trim(),
        full_name: document.getElementById("studentName").value.trim(),
        date_of_birth: document.getElementById("studentDob").value.trim(),
        parent_name: document.getElementById("parentName").value.trim(),
        parent_phone: document.getElementById("parentPhone").value.trim(),
        avatar_base64: document.getElementById("avatarBase64").value.trim(),
        class_id: studentClassSelect.value || null,
      }),
    });
    event.target.reset();
    await refreshAll();
    showMessage("Tạo học sinh thành công.");
  } catch (err) {
    showMessage(err.message, "error");
  }
});

async function processScan(rawText) {
  try {
    const classId = attendanceClassSelect.value;
    await getJSON("/api/attendance/scan", {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText, class_id: classId }),
    });
    await loadAttendanceAndStats();
    showMessage("Điểm danh thành công.");
  } catch (err) {
    showMessage(err.message, "error");
  }
}

document.getElementById("startScanBtn").addEventListener("click", async () => {
  if (!window.Html5Qrcode) return showMessage("Thiếu thư viện quét QR.", "error");
  if (state.scanning) return;

  state.scanner = new Html5Qrcode("reader");
  try {
    await state.scanner.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: { width: 250, height: 250 } },
      (decodedText) => processScan(decodedText),
      () => {},
    );
    state.scanning = true;
    showMessage("Camera đã bật.");
  } catch {
    showMessage("Không bật được camera.", "error");
  }
});

document.getElementById("stopScanBtn").addEventListener("click", async () => {
  if (!state.scanner || !state.scanning) return;
  await state.scanner.stop();
  await state.scanner.clear();
  state.scanner = null;
  state.scanning = false;
  showMessage("Đã tắt camera.");
});

document.getElementById("manualScanBtn").addEventListener("click", () => {
  processScan(document.getElementById("manualScanInput").value);
});

document.getElementById("clearAttendanceBtn").addEventListener("click", async () => {
  try {
    await getJSON("/api/attendance", { method: "DELETE" });
    await loadAttendanceAndStats();
    showMessage("Đã xóa lịch sử điểm danh.");
  } catch (err) {
    showMessage(err.message, "error");
  }
});

attendanceClassSelect.addEventListener("change", () => {
  loadAttendanceAndStats().catch((err) => showMessage(err.message, "error"));
});

updateAuthInfo();
if (state.token) {
  refreshAll().catch((err) => {
    state.token = "";
    state.user = null;
    localStorage.removeItem("mvp_token");
    localStorage.removeItem("mvp_user");
    updateAuthInfo();
    showMessage(`Phiên đăng nhập hết hạn: ${err.message}`, "error");
  });
}
