package com.benchmark.springboot.config;

import java.util.concurrent.TimeUnit;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.util.Timeout;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(AppProperties.class)
public class BenchConfig {

    // Pooled outbound HTTP client for test 3 (GET /catalog -> upstream),
    // capped at 64 to match every other framework's outbound budget (see
    // README "Equal resource budgets").
    @Bean
    public RestClient upstreamClient(AppProperties props) {
        var connectionManager = new PoolingHttpClientConnectionManager();
        connectionManager.setMaxTotal(64);
        connectionManager.setDefaultMaxPerRoute(64);
        connectionManager.setDefaultConnectionConfig(
                ConnectionConfig.custom()
                        .setConnectTimeout(Timeout.of(3, TimeUnit.SECONDS))
                        .setSocketTimeout(Timeout.of(5, TimeUnit.SECONDS))
                        .build());

        // Without a response timeout, a upstream that connects but never sends a
        // body would hang the request (and eventually the whole 64-connection
        // pool) indefinitely.
        RequestConfig requestConfig =
                RequestConfig.custom().setResponseTimeout(Timeout.of(5, TimeUnit.SECONDS)).build();

        CloseableHttpClient httpClient = HttpClients.custom()
                .setConnectionManager(connectionManager)
                .setDefaultRequestConfig(requestConfig)
                // Match the other frameworks (e.g. jero): a service-to-service
                // call to a misbehaving upstream should surface as an error, not
                // be silently followed.
                .disableRedirectHandling()
                .build();

        return RestClient.builder()
                .baseUrl(props.upstreamUrl())
                .requestFactory(new HttpComponentsClientHttpRequestFactory(httpClient))
                .defaultHeader("Authorization", "Bearer " + props.upstreamApiKey())
                .build();
    }
}
