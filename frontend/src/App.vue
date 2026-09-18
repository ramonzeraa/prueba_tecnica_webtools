<script setup>
import { onMounted, ref } from "vue";
import { getSurveyResults } from "./api";

const surveyId = 1;
const data = ref(null);
const loading = ref(false);
const error = ref("");
const fromDate = ref("");
const toDate = ref("");

async function loadResults() {
  if (fromDate.value && toDate.value && fromDate.value > toDate.value) {
    error.value = "La fecha 'desde' no puede ser posterior a 'hasta'.";
    return;
  }

  loading.value = true;
  error.value = "";
  try {
    data.value = await getSurveyResults(surveyId, {
      from: fromDate.value,
      to: toDate.value,
    });
  } catch (exception) {
    error.value = exception.message;
  } finally {
    loading.value = false;
  }
}

onMounted(loadResults);
</script>

<template>
  <main>
    <h1>{{ data?.survey?.title || "Survey results" }}</h1>

    <div class="filters">
      <label>
        Desde
        <input type="date" v-model="fromDate" />
      </label>
      <label>
        Hasta
        <input type="date" v-model="toDate" />
      </label>
      <button @click="loadResults" :disabled="loading">Aplicar filtro</button>
    </div>

    <p v-if="loading">Loading...</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else-if="data">
      <p>{{ data.count }} responses</p>
      <table>
        <thead>
          <tr>
            <th>External ID</th>
            <th>Status</th>
            <th>Submitted</th>
            <th>Answers</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in data.results" :key="item.id">
            <td>{{ item.external_id }}</td>
            <td>{{ item.status }}</td>
            <td>{{ new Date(item.submitted_at).toLocaleString() }}</td>
            <td><code>{{ JSON.stringify(item.answers) }}</code></td>
          </tr>
        </tbody>
      </table>
    </template>
  </main>
</template>

<style>
body {
  margin: 0;
  background: #f5f7fb;
  color: #1f2937;
  font-family: Inter, system-ui, sans-serif;
}

main {
  max-width: 960px;
  margin: 48px auto;
  padding: 32px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 8%);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 12px;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
}

.error {
  color: #b91c1c;
}

.filters {
  display: flex;
  align-items: end;
  gap: 16px;
  margin-bottom: 24px;
}

.filters label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}

.filters button {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  background: #1f2937;
  color: white;
  cursor: pointer;
}

.filters button:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
