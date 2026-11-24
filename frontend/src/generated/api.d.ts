// Generated from ntp_sync_lab.api.app.openapi(); do not edit.
export interface paths {
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Config */
        get: operations["config_api_v1_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/scenarios": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Scenarios */
        get: operations["scenarios_api_v1_scenarios_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/recordings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Recordings */
        get: operations["recordings_api_v1_recordings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/measurements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Measurements */
        post: operations["measurements_api_v1_measurements_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/experiments/delay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Delay */
        post: operations["delay_api_v1_experiments_delay_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/experiments/sync": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Sync */
        post: operations["sync_api_v1_experiments_sync_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/replays": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Replay */
        post: operations["replay_api_v1_replays_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** DelayInput */
        DelayInput: {
            /** Preset */
            preset?: string | null;
            /** True Offset Ms */
            true_offset_ms?: string | null;
            /** Forward Ms */
            forward_ms?: string | null;
            /** Reverse Ms */
            reverse_ms?: string | null;
            /** Processing Ms */
            processing_ms?: string | null;
            /** Reference Unix Ns */
            reference_unix_ns?: string | null;
            /** Round Trip Ms */
            round_trip_ms?: string | null;
            /** Sweep Points */
            sweep_points?: number | null;
            /** Increments Ms */
            increments_ms?: string[] | null;
        };
        /** ErrorInfo */
        ErrorInfo: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Details */
            details: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /** ErrorResult */
        ErrorResult: {
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: "1";
            error: components["schemas"]["ErrorInfo"];
        };
        /** ExchangeData */
        ExchangeData: {
            timestamps: components["schemas"]["Timestamps"];
            /** Estimated Offset Ns */
            estimated_offset_ns: string;
            /** Round Trip Delay Ns */
            round_trip_delay_ns: string;
            /** Client Elapsed Ns */
            client_elapsed_ns: string;
            /** Server Processing Ns */
            server_processing_ns: string;
            /** True Offset Ns */
            true_offset_ns: string | null;
            /** Estimation Error Ns */
            estimation_error_ns: string | null;
        } & {
            [key: string]: components["schemas"]["JsonValue"];
        };
        JsonValue: unknown;
        /** MeasurementInput */
        MeasurementInput: {
            /**
             * Server Id
             * @default pool
             */
            server_id: string;
            /**
             * Timeout Seconds
             * @default 3
             */
            timeout_seconds: number;
        };
        /** ReplayInput */
        ReplayInput: {
            /** Recording Id */
            recording_id?: string | null;
            /** Scenario Id */
            scenario_id?: string | null;
        };
        /** ReplayResult */
        ReplayResult: {
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1";
            /** Experiment */
            experiment: string;
            /**
             * Source
             * @constant
             */
            source: "replay";
            /** Provenance */
            provenance: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Recording */
            recording: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /** Result */
        Result: {
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1";
            /**
             * Experiment
             * @enum {string}
             */
            experiment: "real_exchange" | "network_delay" | "clock_sync";
            /**
             * Source
             * @enum {string}
             */
            source: "live" | "simulation";
            /** Result Id */
            result_id: string;
            /** Created At Utc */
            created_at_utc: string;
            /** Provenance */
            provenance: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Parameters */
            parameters: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            data: components["schemas"]["ExchangeData"];
            /** Warnings */
            warnings: string[];
            /** Assumptions */
            assumptions: string[];
        };
        /** SeriesData */
        SeriesData: {
            /** Points */
            points: components["schemas"]["Result"][];
        };
        /** SeriesResult */
        SeriesResult: {
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1";
            /**
             * Experiment
             * @enum {string}
             */
            experiment: "real_exchange" | "network_delay" | "clock_sync";
            /**
             * Source
             * @enum {string}
             */
            source: "live" | "simulation";
            /** Result Id */
            result_id: string;
            /** Created At Utc */
            created_at_utc: string;
            /** Provenance */
            provenance: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Parameters */
            parameters: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            data: components["schemas"]["SeriesData"];
            /** Warnings */
            warnings: string[];
            /** Assumptions */
            assumptions: string[];
        };
        /** Snapshot */
        Snapshot: {
            /** Reference Unix Ns */
            reference_unix_ns: string;
            /** Virtual Client Unix Ns */
            virtual_client_unix_ns: string;
            /** Client Error Ns */
            client_error_ns: string;
        };
        /** SyncData */
        SyncData: {
            timestamps: components["schemas"]["Timestamps"];
            /** Estimated Offset Ns */
            estimated_offset_ns: string;
            /** Round Trip Delay Ns */
            round_trip_delay_ns: string;
            /** Client Elapsed Ns */
            client_elapsed_ns: string;
            /** Server Processing Ns */
            server_processing_ns: string;
            /** True Offset Ns */
            true_offset_ns: string | null;
            /** Estimation Error Ns */
            estimation_error_ns: string | null;
            /** Initial Client Error Ns */
            initial_client_error_ns: string;
            /** Applied Correction Ns */
            applied_correction_ns: string;
            /** Final Client Error Ns */
            final_client_error_ns: string;
            measurement: components["schemas"]["Result"];
            before: components["schemas"]["Snapshot"];
            after: components["schemas"]["Snapshot"];
            /** Correction Event */
            correction_event: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Timeline */
            timeline: components["schemas"]["TimelinePoint"][];
            /** Explanation */
            explanation: string[];
            /** Conclusion */
            conclusion: string;
        } & {
            [key: string]: components["schemas"]["JsonValue"];
        };
        /** SyncInput */
        SyncInput: {
            /**
             * Client Offset Ms
             * @default 120
             */
            client_offset_ms: string;
            /**
             * Forward Ms
             * @default 20
             */
            forward_ms: string;
            /**
             * Reverse Ms
             * @default 20
             */
            reverse_ms: string;
            /**
             * Processing Ms
             * @default 5
             */
            processing_ms: string;
            /** Reference Unix Ns */
            reference_unix_ns?: string | null;
            /**
             * Mode
             * @default step
             * @constant
             */
            mode: "step";
        };
        /** SyncResult */
        SyncResult: {
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1";
            /**
             * Experiment
             * @enum {string}
             */
            experiment: "real_exchange" | "network_delay" | "clock_sync";
            /**
             * Source
             * @enum {string}
             */
            source: "live" | "simulation";
            /** Result Id */
            result_id: string;
            /** Created At Utc */
            created_at_utc: string;
            /** Provenance */
            provenance: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Parameters */
            parameters: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            data: components["schemas"]["SyncData"];
            /** Warnings */
            warnings: string[];
            /** Assumptions */
            assumptions: string[];
        };
        /** TimelinePoint */
        TimelinePoint: {
            /** Reference Unix Ns */
            reference_unix_ns: string;
            /** Virtual Client Unix Ns */
            virtual_client_unix_ns: string;
            /** Client Error Ns */
            client_error_ns: string;
            /** Sequence */
            sequence: number;
            /** Stage */
            stage: string;
            /** Applied Correction Ns */
            applied_correction_ns: string;
        };
        /** Timestamps */
        Timestamps: {
            /** T1 Unix Ns */
            t1_unix_ns: string;
            /** T2 Unix Ns */
            t2_unix_ns: string;
            /** T3 Unix Ns */
            t3_unix_ns: string;
            /** T4 Unix Ns */
            t4_unix_ns: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    config_api_v1_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    scenarios_api_v1_scenarios_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    recordings_api_v1_recordings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    measurements_api_v1_measurements_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MeasurementInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Result"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    delay_api_v1_experiments_delay_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DelayInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Result"] | components["schemas"]["SeriesResult"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    sync_api_v1_experiments_sync_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SyncInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SyncResult"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
    replay_api_v1_replays_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReplayInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReplayResult"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
            /** @description Gateway Timeout */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResult"];
                };
            };
        };
    };
}
