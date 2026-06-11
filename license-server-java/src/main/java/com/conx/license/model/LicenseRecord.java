package com.conx.license.model;

import jakarta.persistence.*;

@Entity
@Table(name = "licenses")
public class LicenseRecord {

    @Id
    @Column(name = "lic_key", length = 64)
    private String key;

    private String clientName;

    @Column(nullable = false)
    private String status = "active";

    @Column(nullable = false)
    private int maxMachines = 1;

    @Column(columnDefinition = "TEXT")
    private String machinesJson = "{}";

    private String expiresAt;
    private String createdAt;
    private String lastSeen;

    @Column(columnDefinition = "TEXT")
    private String notes = "";

    public String getKey() { return key; }
    public void setKey(String key) { this.key = key; }
    public String getClientName() { return clientName; }
    public void setClientName(String clientName) { this.clientName = clientName; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public int getMaxMachines() { return maxMachines; }
    public void setMaxMachines(int maxMachines) { this.maxMachines = maxMachines; }
    public String getMachinesJson() { return machinesJson; }
    public void setMachinesJson(String machinesJson) { this.machinesJson = machinesJson; }
    public String getExpiresAt() { return expiresAt; }
    public void setExpiresAt(String expiresAt) { this.expiresAt = expiresAt; }
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }
    public String getLastSeen() { return lastSeen; }
    public void setLastSeen(String lastSeen) { this.lastSeen = lastSeen; }
    public String getNotes() { return notes; }
    public void setNotes(String notes) { this.notes = notes; }
}
