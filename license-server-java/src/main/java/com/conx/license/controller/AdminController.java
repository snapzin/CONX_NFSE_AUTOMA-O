package com.conx.license.controller;

import com.conx.license.model.LicenseRecord;
import com.conx.license.repository.LicenseRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

@RestController
@CrossOrigin(origins = "*")
public class AdminController {

    @Value("${admin.user:admin}")
    private String adminUser;

    @Value("${admin.pass:admin}")
    private String adminPass;

    @Autowired
    private LicenseRepository repo;

    @Autowired
    private ObjectMapper mapper;

    @PostMapping("/api/admin")
    public ResponseEntity<Map<String, Object>> handle(
            @RequestHeader(value = "Authorization", required = false) String authHeader,
            @RequestBody(required = false) Map<String, Object> body) {

        if (!checkAuth(authHeader))
            return ResponseEntity.status(401).body(err("Usuário ou senha incorretos"));

        if (body == null) body = new HashMap<>();
        String op = body.getOrDefault("op", "").toString();

        try {
            return switch (op) {
                case "list"          -> handleList();
                case "create"        -> handleCreate(body);
                case "update"        -> handleUpdate(body);
                case "block"         -> handleSetStatus(body, "blocked");
                case "unblock"       -> handleSetStatus(body, "active");
                case "delete"        -> handleDelete(body);
                case "removeMachine" -> handleRemoveMachine(body);
                default -> ResponseEntity.badRequest().body(err("Operação desconhecida: " + op));
            };
        } catch (Exception e) {
            return ResponseEntity.status(500).body(err(e.getMessage()));
        }
    }

    // ── Auth ──────────────────────────────────────────────────────────────────

    private boolean checkAuth(String authHeader) {
        if (authHeader == null || !authHeader.startsWith("Basic ")) return false;
        try {
            String decoded = new String(Base64.getDecoder().decode(authHeader.substring(6)));
            int colon = decoded.indexOf(':');
            if (colon < 0) return false;
            return adminUser.equals(decoded.substring(0, colon))
                && adminPass.equals(decoded.substring(colon + 1));
        } catch (Exception e) { return false; }
    }

    // ── Handlers ──────────────────────────────────────────────────────────────

    private ResponseEntity<Map<String, Object>> handleList() {
        List<LicenseRecord> recs = repo.findAll();
        recs.sort(Comparator.comparing(r -> (r.getClientName() == null ? "" : r.getClientName())));
        List<Map<String, Object>> items = recs.stream().map(this::toMap).collect(Collectors.toList());
        Map<String, Object> res = new LinkedHashMap<>();
        res.put("ok", true);
        res.put("total", items.size());
        res.put("items", items);
        return ResponseEntity.ok(res);
    }

    private ResponseEntity<Map<String, Object>> handleCreate(Map<String, Object> body) {
        Object rawKey = body.get("key");
        String key = (rawKey != null && !rawKey.toString().isBlank())
            ? normalizeKey(rawKey.toString()) : genKey();

        if (repo.existsById(key))
            return ResponseEntity.status(409).body(err("Chave já existe."));

        LicenseRecord rec = new LicenseRecord();
        rec.setKey(key);
        rec.setClientName(body.getOrDefault("clientName", "").toString().trim());
        rec.setStatus("active");
        rec.setMaxMachines(Math.max(1, toInt(body.get("maxMachines"), 1)));
        rec.setMachinesJson("{}");
        rec.setExpiresAt(calcExpiry(body.get("days")));
        rec.setCreatedAt(Instant.now().toString());
        rec.setNotes(body.getOrDefault("notes", "").toString());
        repo.save(rec);

        Map<String, Object> res = new LinkedHashMap<>();
        res.put("ok", true);
        res.put("key", key);
        res.put("keyFmt", formatKey(key));
        res.put("record", toMap(rec));
        return ResponseEntity.ok(res);
    }

    private ResponseEntity<Map<String, Object>> handleUpdate(Map<String, Object> body) throws Exception {
        String key = normalizeKey(str(body.get("key")));
        LicenseRecord rec = repo.findById(key).orElseThrow(() -> new Exception("Chave não encontrada."));

        if (body.containsKey("clientName")) rec.setClientName(str(body.get("clientName")).trim());
        if (body.containsKey("status"))     rec.setStatus("blocked".equals(body.get("status")) ? "blocked" : "active");
        if (body.containsKey("maxMachines")) rec.setMaxMachines(Math.max(1, toInt(body.get("maxMachines"), rec.getMaxMachines())));
        if (body.containsKey("notes"))       rec.setNotes(str(body.get("notes")));

        if (body.containsKey("expiresAt")) {
            Object ea = body.get("expiresAt");
            rec.setExpiresAt(ea == null || ea.toString().isBlank() ? null : ea.toString());
        } else if (body.containsKey("days")) {
            Object d = body.get("days");
            if (d == null) {
                rec.setExpiresAt(null);
            } else {
                String ds = d.toString();
                if (!ds.isBlank()) {
                    try {
                        double days = Double.parseDouble(ds);
                        rec.setExpiresAt(days <= 0 ? null : Instant.now().plus((long) days, ChronoUnit.DAYS).toString());
                    } catch (NumberFormatException ignored) {}
                }
            }
        }

        repo.save(rec);
        return ResponseEntity.ok(ok("record", toMap(rec)));
    }

    private ResponseEntity<Map<String, Object>> handleSetStatus(Map<String, Object> body, String status) throws Exception {
        String key = normalizeKey(str(body.get("key")));
        LicenseRecord rec = repo.findById(key).orElseThrow(() -> new Exception("Chave não encontrada."));
        rec.setStatus(status);
        repo.save(rec);
        return ResponseEntity.ok(ok("status", status));
    }

    private ResponseEntity<Map<String, Object>> handleDelete(Map<String, Object> body) {
        repo.deleteById(normalizeKey(str(body.get("key"))));
        return ResponseEntity.ok(ok());
    }

    private ResponseEntity<Map<String, Object>> handleRemoveMachine(Map<String, Object> body) throws Exception {
        String key = normalizeKey(str(body.get("key")));
        String machineId = str(body.get("machine_id"));
        LicenseRecord rec = repo.findById(key).orElseThrow(() -> new Exception("Chave não encontrada."));

        TypeReference<Map<String, Object>> tr = new TypeReference<>() {};
        Map<String, Object> machines = mapper.readValue(
            rec.getMachinesJson() == null ? "{}" : rec.getMachinesJson(), tr);
        machines.remove(machineId);
        rec.setMachinesJson(mapper.writeValueAsString(machines));
        repo.save(rec);
        return ResponseEntity.ok(ok("record", toMap(rec)));
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    Map<String, Object> toMap(LicenseRecord rec) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("key", rec.getKey());
        m.put("keyFmt", formatKey(rec.getKey()));
        m.put("clientName", rec.getClientName() == null ? "" : rec.getClientName());
        m.put("status", rec.getStatus() == null ? "active" : rec.getStatus());
        m.put("maxMachines", rec.getMaxMachines());
        Map<String, Object> machines = parseMachines(rec.getMachinesJson());
        m.put("machines", machines);
        m.put("machineCount", machines.size());
        m.put("expiresAt", rec.getExpiresAt());
        m.put("createdAt", rec.getCreatedAt());
        m.put("lastSeen", rec.getLastSeen());
        m.put("notes", rec.getNotes() == null ? "" : rec.getNotes());
        return m;
    }

    Map<String, Object> parseMachines(String json) {
        try {
            TypeReference<Map<String, Object>> tr = new TypeReference<>() {};
            return mapper.readValue(json == null || json.isBlank() ? "{}" : json, tr);
        } catch (Exception e) { return new HashMap<>(); }
    }

    public static String normalizeKey(String k) {
        return k == null ? "" : k.toUpperCase().replaceAll("[^A-Z0-9]", "");
    }

    public static String formatKey(String k) {
        String n = normalizeKey(k);
        List<String> parts = new ArrayList<>();
        for (int i = 0; i < n.length(); i += 4) parts.add(n.substring(i, Math.min(i + 4, n.length())));
        return String.join("-", parts);
    }

    private static String genKey() {
        String alf = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        StringBuilder sb = new StringBuilder("NFSE");
        Random rnd = new Random();
        for (int i = 0; i < 16; i++) sb.append(alf.charAt(rnd.nextInt(alf.length())));
        return sb.toString();
    }

    private static String calcExpiry(Object daysObj) {
        if (daysObj == null) return null;
        String s = daysObj.toString();
        if (s.isBlank() || "null".equals(s)) return null;
        try {
            double d = Double.parseDouble(s);
            return d <= 0 ? null : Instant.now().plus((long) d, ChronoUnit.DAYS).toString();
        } catch (Exception e) { return null; }
    }

    private static String str(Object o) { return o == null ? "" : o.toString(); }

    private static int toInt(Object o, int fallback) {
        if (o == null) return fallback;
        try { return (int) Double.parseDouble(o.toString()); } catch (Exception e) { return fallback; }
    }

    private static Map<String, Object> err(String msg) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ok", false);
        m.put("message", msg);
        return m;
    }

    private static Map<String, Object> ok(Object... pairs) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ok", true);
        for (int i = 0; i < pairs.length; i += 2) m.put(pairs[i].toString(), pairs[i + 1]);
        return m;
    }
}
