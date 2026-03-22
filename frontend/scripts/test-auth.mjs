import assert from "node:assert";

// Backend is confirmed at http://127.0.0.1:8000
const BACKEND_URL = "http://127.0.0.1:8000";

async function runTests() {
  console.log("Starting Auth Integration Tests (via Backend)...");
  
  const uniqueSuffix = Date.now().toString().slice(-6);
  const testEmail = `test-${uniqueSuffix}@example.com`;
  const testPassword = "TestPassword123!";
  const testFirstName = "Test";
  const testLastName = "User";

  try {
    // 1. Test Registration
    console.log(`Testing Registration with email: ${testEmail}...`);
    const regRes = await fetch(`${BACKEND_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: testEmail,
        password: testPassword,
        first_name: testFirstName,
        last_name: testLastName,
        avatar_url: null,
      }),
    });
    
    const regData = await regRes.json();
    if (regRes.status !== 201) {
       console.error("Registration failed:", JSON.stringify(regData, null, 2));
       process.exit(1);
    }
    assert.strictEqual(regRes.status, 201);
    assert.strictEqual(regData.email, testEmail);
    console.log("✅ Registration Successful");

    // 2. Test Login
    console.log("Testing Login...");
    const loginRes = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: testEmail,
        password: testPassword,
      }),
    });
    
    const loginData = await loginRes.json();
    if (loginRes.status !== 201) {
       console.error("Login failed:", JSON.stringify(loginData, null, 2));
       process.exit(1);
    }
    assert.strictEqual(loginRes.status, 201);
    assert.ok(loginData.access_token);
    console.log("✅ Login Successful");

    console.log("\nALL TESTS PASSED SUCCESSFULLY");
  } catch (error) {
    console.error("❌ Test Failed:", error);
    process.exit(1);
  }
}

runTests();
