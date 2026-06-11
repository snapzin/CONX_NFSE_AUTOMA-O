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
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@CrossOrigin(origins = "*")
public class ValidateController {

    private static final String CONTACT = "conxcontabil@gmail.com";
    private static final int MAX_REQ = 30;
    private static final long WINDOW_MS = 60_000;

    private final Map<String, long[]> hits = new ConcurrentHashMap<>();

    @Value("${client.secret:}")
    private String clientSecret;

    @Value("${valid.keys:}")
    private String validKeysEnv;

    @Autowired
    private LicenseRepository repo;

    @Autowired
    private ObjectMapper mapper;

    @PostMapping("/api/validate")
    public ResponseEntity<Map<String, Object>> validate(
            @RequestHeader(value = "x-forwarded-for", required = false) String forwardedFor,
            @RequestHeader(value = "x-client-secret", required = false) String secret,
            @RequestBody(required = false) Map<String, Object> body) {

        if (clientSecret != null && !clientSecret.isBlank() && !clientSecret.equals(secret))
            return ResponseEntity.status(403).body(invalid("Acesso não autorizado"));

        String ip = (forwardedFor != null ? forwardedFor.split(",")[0].trim() : "unknown");
        if (isRateLimited(ip))
            return ResponseEntity.status(429).body(invalid("Muitas requisições. Tente novamente."));

        if (body == null) body = new HashMap<>();
        Object rawKey = body.get("key");
        if (rawKey == null || rawKey.toString().isBlank())
            return ResponseEntity.badRequest().body(invalid("Chave não informada"));

        String key = AdminController.normalizeKey(rawKey.toString());
        String mid = body.getOrDefault("machine_id", "unknown").toString();

        try {
            Optional<LicenseRecord> opt = repo.findById(key);

            if (opt.isEmpty()) {
                if (legacyKeys().contains(key))
                    return ResponseEntity.ok(valid());
                return ResponseEntity.ok(invalid("Chave inválida ou expirada. Contato: " + CONTACT));
            }

            LicenseRecord rec = opt.get();

            if ("blocked".equals(rec.getStatus()))
                return ResponseEntity.ok(invalid("Licença bloqueada. Contato: " + CONTACT));

            if (rec.getExpiresAt() != null && Instant.now().isAfter(Instant.parse(rec.getExpiresAt())))
                return ResponseEntity.ok(invalid("Licença expirada. Contato: " + CONTACT));

            TypeReference<Map<String, Object>> tr = new TypeReference<>() {};
            Map<String, Object> machines = mapper.readValue(
                rec.getMachinesJson() == null ? "{}" : rec.getMachinesJson(), tr);

            String now = Instant.now().toString();

            if (machines.containsKey(mid)) {
                @SuppressWarnings("unchecked")
                Map<String, Object> mInfo = (Map<String, Object>) machines.get(mid);
                mInfo.put("lastSeen", now);
            } else if (machines.size() < rec.getMaxMachines()) {
                Map<String, Object> mInfo = new LinkedHashMap<>();
                mInfo.put("firstSeen", now);
                mInfo.put("lastSeen", now);
                machines.put(mid, mInfo);
            } else {
                return ResponseEntity.ok(invalid(
                    "Limite de " + rec.getMaxMachines() + " máquina(s) atingido. Contato: " + CONTACT));
            }

            rec.setMachinesJson(mapper.writeValueAsString(machines));
            rec.setLastSeen(now);
            repo.save(rec);

            return ResponseEntity.ok(valid());

        } catch (Exception e) {
            if (legacyKeys().contains(key)) return ResponseEntity.ok(valid());
            return ResponseEntity.ok(invalid("Servidor indisponível. Tente novamente."));
        }
    }

    private boolean isRateLimited(String ip) {
        long now = System.currentTimeMillis();
        long[] e = hits.getOrDefault(ip, new long[]{0, now});
        if (now - e[1] > WINDOW_MS) { hits.put(ip, new long[]{1, now}); return false; }
        e[0]++;
        hits.put(ip, e);
        return e[0] > MAX_REQ;
    }

    private Set<String> legacyKeys() {
        Set<String> s = new HashSet<>();
        if (validKeysEnv != null) {
            for (String k : validKeysEnv.split(","))
                if (!k.isBlank()) s.add(AdminController.normalizeKey(k.trim()));
        }
        return s;
    }

    private static Map<String, Object> valid() {
        return Map.of("valid", true, "message", "Licença válida.");
    }

    private static Map<String, Object> invalid(String msg) {
        return Map.of("valid", false, "message", msg);
    }
}
