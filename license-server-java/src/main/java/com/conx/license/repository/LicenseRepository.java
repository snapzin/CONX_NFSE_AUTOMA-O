package com.conx.license.repository;

import com.conx.license.model.LicenseRecord;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LicenseRepository extends JpaRepository<LicenseRecord, String> {
}
